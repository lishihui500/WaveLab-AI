"""Acceptance-tool risk tests, never measured AI or GUI benchmark runs.

Only temporary test documents are altered. No rendering is required.
"""
from pathlib import Path
import importlib.util
import json
import shutil
import pytest

ROOT=Path(__file__).resolve().parents[1]
MODULE=importlib.util.spec_from_file_location('stage03f_validate',ROOT/'scripts/stage03f_validate.py')
acceptance=importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(acceptance)

def test_numpy_geometry_scalars_are_json_serializable(tmp_path):
    import numpy as np
    target=tmp_path/'geometry.json'
    acceptance.dump(target,dict(inside_figure=np.bool_(True),coordinate=np.float64(1.5)))
    assert json.loads(target.read_text(encoding='utf-8'))==dict(inside_figure=True,coordinate=1.5)

def test_geometry_excludes_locator_ticks_not_selected_for_draw():
    from matplotlib.figure import Figure
    from matplotlib.ticker import FixedLocator
    fig=Figure();ax=fig.add_subplot();ax.set_xlim(1.25,1.85)
    ax.xaxis.set_major_locator(FixedLocator([1.2,1.4,1.6,1.95]))
    labels,excluded=acceptance.drawn_tick_labels(ax.xaxis)
    assert [row['location'] for row in excluded]==[1.2,1.95]
    assert len(labels)==2
    assert all('actual draw' in row['reason'] for row in excluded)

def test_geometry_still_rejects_clipped_actually_drawn_tick():
    from types import SimpleNamespace
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.ticker import FixedLocator
    fig=Figure(figsize=(2,1),dpi=100);FigureCanvasAgg(fig)
    ax=fig.add_axes([0,.3,.9,.6]);ax.set_xlim(0,1)
    ax.xaxis.set_major_locator(FixedLocator([0,.5,1]))
    ax.set_xticklabels(['DRAWN_CLIPPED_LABEL','middle','end'])
    result=SimpleNamespace(figure=fig,axes={'p':ax},inset_axes={})
    view=SimpleNamespace(panels=[SimpleNamespace(id='p',insets=[])])
    geometry=acceptance.geometry_checks(result,view,'en')
    clipped=[row for row in geometry['texts'] if row['kind']=='xtick' and row['text']=='DRAWN_CLIPPED_LABEL']
    assert len(clipped)==1 and not clipped[0]['inside_figure']

def fixture(tmp_path,task):
    folder=tmp_path/'candidate'
    shutil.copytree(ROOT/'reports/stage_03F/baselines'/task,folder)
    path=folder/'project.json';path.chmod(0o666)
    doc=json.loads(path.read_text(encoding='utf-8'))
    if task=='F02':
        for phase,panel in zip('ABC',doc['figure']['panels']):
            panel['title_i18n']=dict(zh=phase+'相',en='Phase '+phase)
            for i,series in enumerate(panel['series']):
                series.update(color=['#0072B2','#D55E00'][i],linestyle=['-','--'][i],linewidth_pt=1.2)
    elif task=='F03':
        for i,panel in enumerate(doc['figure']['panels']):
            panel['insets']=[dict(id=f'unit_test_inset_{i}',channel_ids=[s['channel_id'] for s in panel['series']],xlim_s=[1.4,1.44],ylim=None,bounds=[.56,.52,.4,.4],show_region=True,show_connectors=True)]
    return path,doc

def run(tmp_path,path,doc,task):
    path.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
    return acceptance.validate(task,path,tmp_path/'verification',False)

@pytest.mark.parametrize('task',['F02','F03'])
def test_acceptance_control_and_roundtrip(tmp_path,task):
    path,doc=fixture(tmp_path,task)
    result=run(tmp_path,path,doc,task)
    assert result['passed']
    assert result['checks']['save_close_reopen_arrays']
    assert result['visual_acceptance']=='PENDING_ACTUAL_IMAGE_INSPECTION'

def test_unrelated_change_is_rejected(tmp_path):
    path,doc=fixture(tmp_path,'F02');doc['figure']['time_axis']['xlim']=[1.3,1.7]
    result=run(tmp_path,path,doc,'F02')
    assert not result['passed']
    assert not result['checks']['all_unrelated_fields_unchanged']

@pytest.mark.parametrize('mutation',['missing','repeated_across_panels'])
def test_missing_or_repeated_global_channel_is_rejected(tmp_path,mutation):
    path,doc=fixture(tmp_path,'F02');panels=doc['figure']['panels']
    if mutation=='missing':panels[1]['series'].pop()
    else:panels[1]['series'][0]=dict(panels[0]['series'][0])
    result=run(tmp_path,path,doc,'F02')
    assert not result['passed']
    assert not result['checks']['no_missing_or_duplicate_series']

def test_different_inset_bounds_are_rejected(tmp_path):
    path,doc=fixture(tmp_path,'F03');doc['figure']['panels'][1]['insets'][0]['bounds']=[.5,.52,.4,.4]
    result=run(tmp_path,path,doc,'F03')
    assert not result['passed'] and not result['checks']['same_bounds']

@pytest.mark.parametrize('update_manifest_hash',[False,True])
def test_altered_source_values_are_rejected_even_if_hash_updated(tmp_path,update_manifest_hash):
    import hashlib
    path,doc=fixture(tmp_path,'F02');manifest=doc['figure']['datasets'][0]
    source=path.parent/manifest['source_path'];source.chmod(0o666)
    lines=source.read_text(encoding='utf-8').splitlines();row=lines[1].split(',');row[1]=str(float(row[1])+1);lines[1]=','.join(row)
    source.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if not update_manifest_hash:
        with pytest.raises(ValueError):run(tmp_path,path,doc,'F02')
    else:
        manifest['source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        result=run(tmp_path,path,doc,'F02')
        assert not result['passed']
        assert not result['checks']['dataset_identity_metadata_unchanged']
        assert not result['checks']['data_'+manifest['dataset_id']]

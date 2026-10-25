"""FigureSpec 0.4 policy: data attributes once, independent plot styles."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from wavelab.domain.figure import FigureSpec
from wavelab.workbench import Workbench
from wavelab.render.engine import render_figure, export_figure
from wavelab.commands.plot import Action,Plan,prepare,sample_hashes,tool_definitions
from wavelab.local_bridge import execute,status
from wavelab.channel_properties_ui import apply_channel_table

ROOT=Path(__file__).resolve().parents[1]
REAL=ROOT/'.wavelab/projects/汇报绘图案例'


@pytest.fixture
def w(tmp_path):
    document=json.loads((REAL/'project.json').read_text(encoding='utf-8'))
    m=next(m for m in document['figure']['datasets'] if len(m['channels'])==3 and all(c.get('quantity') and c['quantity']['zh']=='电压' for c in m['channels']))
    work=Workbench(tmp_path)
    work.import_bytes((REAL/m['source_path']).read_bytes(),'真实三通道电压.txt')
    ids=[c.channel_id for c in work.spec.datasets[0].channels]
    work.set_channel_properties({cid:dict(display_name=n,quantity_name='voltage',unit='kV') for cid,n in zip(ids,['A相电压','B相电压','C相电压'])})
    work.assign_channels('panel_1',ids)
    return work


def test_all_references_follow_but_styles_are_independent(w):
    ids=[c.channel_id for c in w.spec.datasets[0].channels]
    assert len({c.raw_header for c in w.spec.datasets[0].channels})==1
    w.create_panel('second');w.assign_channels('second',ids)
    w.update(['panels',0,'series',0,'color'],'blue')
    w.update(['panels',1,'series',0,'color'],'red')
    w.update(['panels',1,'series',0,'linestyle'],'--')
    w.upsert_inset('panel_1',dict(id='zoom',xlim_s=[1.32,1.34]))
    hashes=sample_hashes(w); before=w.spec
    w.set_channel_properties({ids[0]:dict(display_name='A相统一名称')})
    changed=w.spec; image=render_figure(w.spec,w.datasets)
    assert image.lines['panel_1',ids[0]].get_label()==image.lines['second',ids[0]].get_label()=='A相统一名称'
    assert image.lines['panel_1',ids[0]].get_color()=='blue'
    assert image.lines['second',ids[0]].get_color()=='red'
    assert image.lines['second',ids[0]].get_linestyle()=='--'
    assert any(l.get_label()=='A相统一名称' for a in image.axes['panel_1'].child_axes for l in a.lines)
    assert sample_hashes(w)==hashes
    w.undo();assert w.spec==before
    w.redo();assert w.spec==changed


def test_save_has_no_parallel_overrides(w,tmp_path):
    path=w.save_project('canonical')
    data=json.loads(path.read_text(encoding='utf-8'))['figure']
    assert data['schema_version']=='0.4'
    for p in data['panels']:
        assert not set(p)&{'display_unit','quantity_preset_id','ylabel','ylabel_i18n','ylabel_mode'}
        for s in p['series']:
            assert not set(s)&{'label','label_i18n','legend_source','unit','physical_role','confirmation_source'}
    assert not set(data['legend'])&{'show_units','axis_show_units'}
    assert all('unit' not in c['quantity'] for m in data['datasets'] for c in m['channels'])
    fresh=Workbench(tmp_path/'new_process');fresh.open_project(path)
    assert [c.display_name for c in fresh.spec.datasets[0].channels]==['A相电压','B相电压','C相电压']
    assert render_figure(fresh.spec,fresh.datasets).axes['panel_1'].get_ylabel()=='电压 (kV)'
    fresh.set_languages('en','en')
    image=render_figure(fresh.spec,fresh.datasets)
    assert image.axes['panel_1'].get_ylabel()=='Voltage (kV)'
    assert [l.get_label() for l in image.axes['panel_1'].lines]==['A相电压','B相电压','C相电压']
    for ext in ('png','pdf','svg'): export_figure(image,tmp_path/f'result.{ext}')


def test_mixed_quantities_do_not_block_metadata_or_pick_first(w):
    ids=[c.channel_id for c in w.spec.datasets[0].channels]
    hashes=sample_hashes(w)
    w.set_channel_properties({ids[0]:dict(quantity_name='current',unit='kA')})
    image=render_figure(w.spec,w.datasets)
    assert image.axes['panel_1'].get_ylabel()=='混合物理量'
    assert any('不同物理量' in x for x in image.warnings)
    assert sample_hashes(w)==hashes
    w.set_channel_properties({cid:dict(quantity_name='current',unit='kA') for cid in ids})
    assert render_figure(w.spec,w.datasets).axes['panel_1'].get_ylabel()=='电流 (kA)'


def test_mixed_units_really_scale_display_arrays_and_inset(w):
    ids=[c.channel_id for c in w.spec.datasets[0].channels]
    raw=w.datasets[w.spec.datasets[0].dataset_id].values(ids[0]).copy()
    w.set_channel_properties({ids[0]:dict(unit='V')})
    w.upsert_inset('panel_1',dict(id='zoom',xlim_s=[1.32,1.34]))
    image=render_figure(w.spec,w.datasets)
    assert image.axes['panel_1'].get_ylabel()=='电压 (kV)'
    np.testing.assert_array_equal(image.lines['panel_1',ids[0]].get_ydata(),raw*.001)
    np.testing.assert_array_equal(w.datasets[w.spec.datasets[0].dataset_id].values(ids[0]),raw)
    child=image.axes['panel_1'].child_axes[0]
    assert child.lines[0].get_label()=='A相电压'
    w.set_channel_properties({ids[0]:dict(unit='pu')})
    image=render_figure(w.spec,w.datasets)
    assert any('无法直接换算' in x for x in image.warnings)


def test_legacy_migration_prefers_channel_and_converts_old_ranges(w,tmp_path):
    old=w.spec.model_dump(mode='json');old['schema_version']='0.3'
    p=old['panels'][0];p.update(display_unit='V',quantity_preset_id='voltage',ylabel_mode='preset',ylabel_i18n=dict(zh='旧标题',en='Old'),ylim=[1000.,5000.])
    p['series'][0].update(label_i18n=dict(zh='冲突图例',en='Other'),legend_source='custom',unit='kV')
    migrated=FigureSpec.model_validate(old)
    assert migrated.panels[0].ylim==(1.,5.)
    assert any('冲突图例' in x for x in migrated.migration_notes)
    assert migrated.datasets[0].channels[0].display_name=='A相电压'
    assert migrated.panels[0].series[0].label_i18n.zh==''
    again=FigureSpec.model_validate_json(migrated.model_dump_json())
    assert not again.migration_notes
    assert again.panels[0].ylim==(1.,5.)


def test_no_inference_from_old_axis_or_ambiguous_names(w):
    old=w.spec.model_dump(mode='json');old['schema_version']='0.3'
    for c in old['datasets'][0]['channels']: c.update(unit=None,quantity=None)
    old['panels'][0].update(display_unit='kV',quantity_preset_id='voltage',ylabel_mode='preset',ylim=[1.,2.])
    old['panels'][0]['series'][0].update(label_i18n={'zh':'名称甲','en':'name B'},unit='V')
    result=FigureSpec.model_validate(old)
    assert all(c.quantity is None and c.unit is None for c in result.datasets[0].channels)
    assert result.panels[0].ylim is None
    assert result.migration_notes


@pytest.mark.parametrize('field,value',[('label_i18n',{'zh':'bad'}),('unit','A'),('legend_source','custom')])
def test_no_new_curve_overrides(w,field,value):
    data=w.spec.model_dump(mode='json');data['panels'][0]['series'][0][field]=value
    with pytest.raises(ValueError,match='通道属性'): FigureSpec.model_validate(data)
    with pytest.raises(ValueError,match='通道属性'): w.update(['panels',0,'series',0,field],value)


def test_ai_mcp_cannot_create_parallel_labels(w):
    schema=tool_definitions()
    assert 'label_i18n' not in schema['allowed_changes']['update_series']
    assert 'ylabel_i18n' not in schema['allowed_changes']['update_panel']
    assert 'set_axis_quantity' not in schema['allowed_changes']
    cid=w.spec.datasets[0].channels[0].channel_id
    with pytest.raises(ValueError):prepare(w,Plan(summary='bad',actions=[Action(action='update_series',panel_id='panel_1',channel_id=cid,changes={'label_i18n':{'zh':'bad'}})]))
    state=status(w,'live')
    result=execute(w,'live','apply_plot_actions',dict(expected_revision=w.revision,expected_project_epoch=w.project_epoch,
        expected_fingerprint=state['fingerprint'],user_request='统一改名',actions=[dict(action='set_channel_properties',channel_id=cid,changes={'display_name':'统一改名'})]))
    assert result['result']['samples_unchanged']
    assert execute(w,'live','get_channel_metadata',dict(channel_id=cid))['channel']['display_name']=='统一改名'


def test_table_transaction_rejects_stale_or_relabelled_id(w):
    m=w.spec.datasets[0]
    rows=[dict(channel_id=c.channel_id,display_name=c.display_name,quantity_name='voltage',unit=c.unit) for c in m.channels]
    data=dict(binding=w.project_epoch,revision=w.revision,rows=rows)
    data['rows'][0]['display_name']='统一'
    apply_channel_table(w,m,data)
    with pytest.raises(ValueError,match='变化'):apply_channel_table(w,m,data)


def test_gui_has_only_component_and_styles(w):
    at=AppTest.from_file(ROOT/'app.py',default_timeout=45)
    at.session_state['workbench']=w;at.run()
    assert not at.exception
    labels=[getattr(e,'label','') for kind in ('text_input','selectbox','checkbox','button','expander') for e in getattr(at,kind)]
    forbidden={'确认物理映射','Y轴分类','Y轴物理量预设','Y 轴显示单位（换算刻度）','Y 轴显示跟随源单位',
        'Y 轴标签来源','自定义 Y 轴双语标题','图例显示单位','图例 · 中文','图例 · English','图例使用通道名称'}
    assert not forbidden.intersection(labels)
    assert '曲线与图例样式' in labels and 'Y 轴范围与刻度' in labels
    assert at.get('component_instance')


@pytest.mark.parametrize('project',['汇报绘图案例','汇报绘图案例_复杂案例','Stage03F_GUI_F01_R1','Stage04_V2_MCP_T4_R1'])
def test_real_and_historical_read_render_no_source_change(tmp_path,project):
    folder=ROOT/'.wavelab/projects'/project
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
    work=Workbench(tmp_path);work.open_project(folder/'project.json')
    result=render_figure(work.spec,work.datasets)
    assert result.figure.axes
    after={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
    assert before==after

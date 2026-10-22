from pathlib import Path
import hashlib
import json

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from wavelab.workbench import Workbench
from wavelab.commands.plot import Action, Plan, prepare, apply_proposal, fingerprint, sample_hashes
from wavelab.local_bridge import execute
from wavelab.render.engine import render_figure, export_figure

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def real(tmp_path):
    w = Workbench(tmp_path)
    source = ROOT/'test/fixtures/X相下桥臂故障电流.txt'
    w.import_bytes(source.read_bytes(), source.name)
    ids = [c.channel_id for c in w.spec.datasets[0].channels[:3]]
    w.assign_channels('panel_1', ids)
    w.create_panel('repeat')
    w.assign_channels('repeat', ids)
    data = next(iter(w.datasets.values()))
    w.upsert_inset('panel_1', dict(id='zoom', xlim_s=[float(data.time_s[1]), float(data.time_s[-2])]))
    return w, ids


def confirm(w, ids):
    w.set_channel_properties({cid: dict(display_name=f'I{i+1}', quantity_name='current', unit='kA') for i,cid in enumerate(ids)})


def test_real_batch_follow_override_undo_reopen_export(real, tmp_path):
    w, ids = real
    with pytest.raises(ValueError):
        w.update(['panels',1,'series',0,'label_i18n'], dict(zh='特殊图例', en='Special'))
    before = w.spec
    hashes = sample_hashes(w)
    history = len(w.undo_stack)
    confirm(w, ids)
    assert len(w.undo_stack) == history+1
    for c in w.spec.datasets[0].channels[:3]:
        assert c.unit == c.quantity.unit == 'kA' and c.quantity.en == 'Current'
    result = render_figure(w.spec,w.datasets)
    assert result.lines[('panel_1',ids[0])].get_label() == 'I1'
    assert result.lines[('repeat',ids[0])].get_label() == 'I1'
    assert any(line.get_label() == 'I1' for ax in result.axes['panel_1'].child_axes for line in ax.lines)
    assert sample_hashes(w) == hashes
    changed = w.spec
    w.undo(); assert w.spec == before
    w.redo(); assert w.spec == changed
    saved = w.save_project('isolated')
    reopened = Workbench(tmp_path/'fresh'); reopened.open_project(saved)
    assert sample_hashes(reopened) == hashes
    assert [c.model_dump() for c in reopened.spec.datasets[0].channels] == [c.model_dump() for c in changed.datasets[0].channels]
    image = render_figure(reopened.spec,reopened.datasets)
    export_figure(image,tmp_path/'verified.pdf')
    export_figure(image,tmp_path/'verified.svg')
    assert 'I1' in (tmp_path/'verified.svg').read_text(encoding='utf-8')
    assert (tmp_path/'verified.pdf').stat().st_size > 1000


def test_quantity_without_unit_and_unit_clear_do_not_infer(real):
    w, ids = real
    w.set_channel_properties({ids[0]:dict(quantity_name='current')})
    c=w.spec.datasets[0].channels[0]
    assert c.quantity.en=='Current' and c.unit is None and c.quantity.unit is None
    confirm(w,ids)
    w.set_channel_properties({cid:dict(unit=None) for cid in ids})
    assert w.spec.datasets[0].channels[0].quantity.en=='Current'
    assert all(c.unit is None for c in w.spec.datasets[0].channels[:3])


def test_same_headers_other_dataset_identity_and_mcp_readback(real):
    w, ids = real
    raw = (ROOT/'test/fixtures/X相下桥臂故障电流.txt').read_bytes()
    other = w.import_bytes(raw,'copy.txt')
    confirm(w,ids)
    assert all(c.unit is None for c in next(m for m in w.spec.datasets if m.dataset_id==other).channels)
    c = w.spec.datasets[0].channels[0]
    read = execute(w,'test','get_channel_metadata',dict(channel_id=c.channel_id))
    assert read['channel']['display_name']==c.display_name
    assert read['channel']['unit']==c.unit and read['channel']['quantity']['zh']==c.quantity.zh
    status=execute(w,'test','get_wavelab_status',{})
    response=execute(w,'test','apply_plot_actions',dict(expected_revision=status['revision'],expected_project_epoch=w.project_epoch,
        expected_fingerprint=status['fingerprint'],user_request='改名',actions=[dict(action='set_channel_properties',channel_id=c.channel_id,changes=dict(display_name='MCP名称'))]))
    assert response['result']['samples_unchanged']
    assert w.spec.datasets[0].channels[0].display_name=='MCP名称'
    conflict=execute(w,'test','apply_plot_actions',dict(expected_revision=status['revision'],expected_project_epoch=w.project_epoch,
        expected_fingerprint=status['fingerprint'],user_request='改名',actions=[dict(action='set_channel_properties',channel_id=c.channel_id,changes=dict(display_name='stale'))]))
    assert conflict['error']=='version_conflict'


def test_atomic_bad_units_mixed_quantities_and_explicit_axes(real):
    w, ids = real
    confirm(w,ids)
    before=w.spec
    with pytest.raises(ValueError):
        w.set_channel_properties({ids[0]:dict(display_name='bad',quantity_name='voltage',unit='kA')})
    assert w.spec==before
    # Same-unit custom quantities must not create an automatic unified label.
    w.set_channel_properties({ids[0]:dict(quantity_name='自定义量',unit='kA')})
    from wavelab.units import confirmed_y_axis
    assert confirmed_y_axis(w.spec,w.spec.panels[0],'zh')[0]=='混合物理量'
    confirm(w,ids)
    with pytest.raises(ValueError):
        w.set_axis_quantity('panel_1','current','kA')
    w.set_channel_properties({cid:dict(quantity_name='voltage',unit='kV') for cid in ids})
    assert confirmed_y_axis(w.spec,w.spec.panels[0],'zh')[0]=='电压 (kV)'


def test_mcp_requires_verbatim_source_unit_evidence(real):
    w,ids=real
    plan=Plan(summary='metadata',actions=[Action(action='set_channel_properties',channel_id=ids[0],changes=dict(unit='kA'))])
    with pytest.raises(ValueError,match='原话'):
        prepare(w,plan,'请使用kA显示')


def test_gui_single_entry_batch_and_refill(real):
    w,ids=real
    at=AppTest.from_file(ROOT/'app.py',default_timeout=45)
    at.session_state['workbench']=w
    at.run(); assert not at.exception
    def elem(kind,label): return next(e for e in getattr(at,kind) if e.label==label)
    confirm(w,ids)
    at.run()
    assert not at.exception
    assert [c.display_name for c in w.spec.datasets[0].channels[:3]]==['I1','I2','I3']
    assert any(e.type=='component_instance' for e in at.main)
    assert not any(e.label in ('通道物理量预设','当前通道确认单位') for e in at.selectbox)


@pytest.mark.parametrize('project',['Stage03F_GUI_F01_R1','Stage03F_MCP_F02_R1','Stage04_V2_GUI_T1_R1','Stage04_V2_MCP_T4_R1','汇报绘图案例'])
def test_historical_projects_read_only(tmp_path,project):
    path=ROOT/'.wavelab/projects'/project/'project.json'
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    w=Workbench(tmp_path); w.open_project(path)
    assert w.spec and w.datasets
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before

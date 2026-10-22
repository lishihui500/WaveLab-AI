"""IEEE layout and persistent inset integration acceptance."""
import numpy as np
import pytest
from wavelab.workbench import Workbench
from wavelab.domain import Dataset
from wavelab.domain.figure import FigureSpec, PanelSpec, InsetSpec
from wavelab.render.engine import render_figure, export_figure
from wavelab.render.insets import window_data, window_ylim


@pytest.fixture
def w(tmp_path):
    work = Workbench(tmp_path)
    work.import_bytes(b"Domain,u,u,u,u,u,u\n1,1,2,3,4,5,6\n1.01,2,3,4,5,6,7\n1.02,3,4,5,6,7,8\n1.03,4,5,6,7,8,9", "sample.txt")
    work.assign_channels("panel_1", [c.channel_id for c in work.spec.datasets[0].channels])
    return work


def config(identity="zoom", **kw):
    return dict(id=identity, xlim_s=[1.01, 1.02], **kw)


@pytest.mark.parametrize("legend,axis", [(False,True),(True,True),(True,False)])
def test_unit_positions_custom_labels_and_raw_invariant(w, legend, axis):
    samples = next(iter(w.datasets.values())).samples.copy()
    w.confirm_panel_quantity("panel_1", "电压", "Voltage", "V")
    with pytest.raises(ValueError): w.update(["legend","show_units"],legend)
    w.set_languages(legend="en",axes="en")
    result=render_figure(w.spec,w.datasets)
    assert result.axes['panel_1'].get_ylabel()=='Voltage (V)'
    assert all('(V)' not in line.get_label() for line in result.lines.values())
    with pytest.raises(ValueError): w.update(['panels',0,'ylabel_i18n'],{'en':'User axis'})
    assert all(c.unit == "V" for c in w.spec.datasets[0].channels)
    np.testing.assert_array_equal(next(iter(w.datasets.values())).samples,samples)


def test_three_panels_keep_styles_and_independent_y(w):
    first=w.spec.panels[0]
    w.update(["panels"], [first.model_dump(),PanelSpec(id="p2").model_dump(),PanelSpec(id="p3").model_dump()])
    styles={s.channel_id:(s.color,s.linestyle,s.linewidth_pt) for s in first.series}
    for j,s in enumerate(first.series[2:]):
        w.move_series("panel_1",s.channel_id,"p2" if j<2 else "p3")
    w.update(["panels",1,"ylim"],[0,12])
    result=render_figure(w.spec,w.datasets)
    assert [len(p.series) for p in w.spec.panels]==[2,2,2]
    for p in w.spec.panels:
        for s in p.series:
            assert styles[s.channel_id]==(s.color,s.linestyle,s.linewidth_pt)
    assert result.axes["panel_1"].get_shared_x_axes().joined(*list(result.axes.values())[:2])
    assert result.axes["panel_1"].get_xlabel()==""
    assert result.axes["p2"].get_ylim()==(0,12)


def test_multiple_insets_data_time_sync_lifecycle_and_exports(w,tmp_path,monkeypatch):
    datasets=w.datasets
    def forbidden(*a,**kw): raise AssertionError("No import or AI on local edits")
    monkeypatch.setattr("wavelab.workbench.parse_file",forbidden)
    monkeypatch.setattr("wavelab.ai.manual.ManualExchange.generate",forbidden)
    monkeypatch.setattr("wavelab.ai.assistant.Assistant.propose",forbidden)
    w.upsert_inset("panel_1",config())
    w.upsert_inset("panel_1",config("second",ylim=[0,10],bounds=[0.05,0.1,0.3,0.3]))
    w.update(["panels",0,"series",0,"color"],"red")
    result=render_figure(w.spec,w.datasets)
    assert len(result.axes["panel_1"].child_axes)==2
    np.testing.assert_array_equal(result.inset_axes["zoom"].lines[0].get_xdata(),[1.01,1.02])
    np.testing.assert_array_equal(result.inset_axes["zoom"].lines[0].get_ydata(),[2,3])
    assert result.inset_axes["zoom"].lines[0].get_color()=="red"
    assert result.inset_axes["second"].get_ylim()==(0,10)
    w.update(["time_axis"],dict(mode="relative",unit="ms",event_time_s=1))
    relative=render_figure(w.spec,w.datasets)
    np.testing.assert_allclose(relative.inset_axes["zoom"].get_xlim(),[10,20])
    assert w.spec.panels[0].insets[0].xlim_s==(1.01,1.02)
    w.set_time_unit("s")
    assert next(iter(w.datasets.values())) is next(iter(datasets.values()))
    path=w.save_project("insets");other=Workbench(tmp_path/"other");other.open_project(path)
    assert other.spec.panels==w.spec.panels
    result=render_figure(other.spec,other.datasets)
    for fmt in ("pdf","svg","png"):
        assert export_figure(result,tmp_path/("insets."+fmt)).stat().st_size>1000
    w.remove_inset("panel_1","zoom")
    assert len(render_figure(w.spec,w.datasets).inset_axes)==1
    w.undo();assert len(w.spec.panels[0].insets)==2
    w.redo();assert len(w.spec.panels[0].insets)==1
    assert len(w.spec.datasets)==1


@pytest.mark.parametrize("changes",[dict(xlim_s=[2,1]),dict(xlim_s=[9,10]),dict(bounds=[.9,.9,.4,.4]),dict(xlim_s=[float("nan"),2]),dict(ylim=[2,1])])
def test_rejected_edit_is_atomic(w,changes):
    before=w.spec
    item=config();item.update(changes)
    with pytest.raises(ValueError): w.upsert_inset("panel_1",item)
    assert w.spec==before


def test_nonfinite_constant_empty_hidden_removed_and_multi_panel(w):
    cid=w.spec.panels[0].series[0].channel_id
    data=next(iter(w.datasets.values()));matrix=data.samples.copy()
    matrix[:,1]=[np.nan,np.inf,5,5]
    modified=Dataset(data.manifest,matrix)
    inset=InsetSpec(**config(channel_ids=[cid]))
    curves=window_data(inset,w.spec.panels[0],{data.manifest.dataset_id:modified})
    lo,hi=window_ylim(curves);assert lo<5<hi
    w.upsert_inset("panel_1",config(channel_ids=[cid]))
    first=w.spec.panels[0]
    w.update(["panels"],[first.model_dump(),PanelSpec(id="p2",series=first.series).model_dump()])
    w.upsert_inset("p2",config("other"))
    assert len(render_figure(w.spec,w.datasets).inset_axes)==2
    w.update(["panels",0,"series",0,"visible"],False)
    result=render_figure(w.spec,w.datasets)
    assert "zoom" not in result.inset_axes and any("有效样本" in x for x in result.warnings)
    w.update(["panels"],[w.spec.panels[1].model_dump()])
    assert set(render_figure(w.spec,w.datasets).inset_axes)=={"other"}


def test_gui_create_edit_delete_undo(tmp_path):
    from test_app import loaded,find,click
    at=loaded(tmp_path)
    click(at,"添加局部放大图")
    work=at.session_state["workbench"]
    inset=work.spec.panels[0].insets[0]
    find(at,"selectbox","编辑局部图").select(inset.id).run()
    find(at,"number_input","局部图左侧位置").set_value(0.1)
    click(at,"保存局部放大图")
    assert work.spec.panels[0].insets[0].bounds[0]==.1
    click(at,"删除局部放大图")
    assert not work.spec.panels[0].insets
    click(at,"撤销")
    assert work.spec.panels[0].insets


def test_gesture_revision_relative_mapping_and_single_move_commit(w):
    from wavelab.inset_interaction import apply_gesture
    w.update(["time_axis"],dict(mode="relative",unit="ms",event_time_s=1))
    selection=dict(kind="select",revision=w.revision,panel_id="panel_1",xlim=[10,20],ylim=[0,10])
    pending=apply_gesture(w,selection)
    assert pending["xlim_s"]==(1.01,1.02)
    w.upsert_inset("panel_1",dict(id="zoom",xlim_s=pending["xlim_s"],ylim=pending["ylim"]))
    with pytest.raises(ValueError,match="旧画布"): apply_gesture(w,selection)
    revision=w.revision
    apply_gesture(w,dict(kind="move",revision=revision,panel_id="panel_1",inset_id="zoom",bounds=[.1,.2,.3,.4]))
    assert w.revision==revision+1 and w.spec.panels[0].insets[0].bounds==(.1,.2,.3,.4)
    w.undo();assert w.spec.panels[0].insets[0].bounds==(.56,.52,.4,.4)


@pytest.mark.parametrize("region,connectors",[(False,False),(True,False),(False,True),(True,True)])
def test_region_connector_controls_and_parent_clipping(w,region,connectors):
    w.upsert_inset("panel_1",config(show_region=region,show_connectors=connectors))
    result=render_figure(w.spec,w.datasets)
    assert len(result.inset_axes)==1
    indicators=[a for a in result.axes["panel_1"].artists if hasattr(a,"rectangle")]
    if region or connectors:
        indicator=indicators[0]
        assert indicator.rectangle.get_visible()==region
        assert indicator.rectangle.get_clip_on()
        if not connectors: assert not any(c.get_visible() for c in indicator.connectors)
    else:
        assert not indicators


def test_replaced_loaded_data_invalidates_view_and_inset(w):
    w.upsert_inset("panel_1",config())
    old=next(iter(w.datasets.values()))
    samples=old.samples.copy();samples[:,1]+=100
    w.data[old.manifest.dataset_id]=Dataset(old.manifest,samples)
    new=next(iter(w.datasets.values()))
    assert new is not old
    result=render_figure(w.spec,w.datasets)
    np.testing.assert_array_equal(result.inset_axes["zoom"].lines[0].get_ydata(),[102,103])


def test_inset_subset_removal_and_unknown_reference(w):
    ids=[s.channel_id for s in w.spec.panels[0].series]
    with pytest.raises(ValueError): w.upsert_inset("panel_1",config(channel_ids=["unknown:col_1"]))
    w.upsert_inset("panel_1",config(channel_ids=ids[:2]))
    w.assign_channels("panel_1",ids[1:])
    result=render_figure(w.spec,w.datasets)
    assert len(result.inset_axes["zoom"].lines)==1
    assert result.inset_axes["zoom"].lines[0].get_gid()==ids[1]

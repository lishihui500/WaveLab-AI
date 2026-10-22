"""Panel ordering contract: immutable contents, local UI, structured AI, exports."""
from pathlib import Path
import numpy as np
import pytest
from streamlit.testing.v1 import AppTest
from wavelab.workbench import Workbench
from wavelab.domain.figure import PanelSpec, EventSpec
from wavelab.commands import Plan, prepare, apply_proposal, tool_definitions
from wavelab.panel_order import apply_order_gesture
from wavelab.render.engine import render_figure, export_figure


@pytest.fixture
def w(tmp_path):
    work = Workbench(tmp_path)
    work.import_bytes(b"Domain,u,u,u,u,u,u,v,v,v,v,v\n0,1,2,3,4,5,6,7,8,9,10,11\n1,2,3,4,5,6,7,8,9,10,11,12\n2,3,4,5,6,7,8,9,10,11,12,13", "sample.txt")
    work.map_channels(work.spec.datasets[0].dataset_id,"u","six_arms","synthetic fixture confirmed order","kV")
    work.map_channels(work.spec.datasets[0].dataset_id,"v","numbered","synthetic voltage group","kV")
    ids = [c.channel_id for c in work.spec.datasets[0].channels]
    work.assign_channels("panel_1", ids[6:])
    work.create_panel("panel_2", 0)
    work.assign_channels("panel_2", ids[:6])
    work.upsert_inset("panel_2", dict(id="zoom", xlim_s=[0, 1], bounds=[.1,.2,.3,.4]))
    work.update(["panels",0,"series",0,"color"], "red")
    work.update(["panels",0,"series",0,"linestyle"], "--")
    work.update(["panels",0,"series",0,"linewidth_pt"], 1.7)
    work.update(["panels",0,"ylim"], [0,20])
    work.update(["events"], [EventSpec(time_s=1,label="local",confirmation_source="test",panel_ids=("panel_2",)).model_dump(), EventSpec(time_s=0,label="global",confirmation_source="test").model_dump()])
    return work


def ids(w):
    return [p.id for p in w.spec.panels]


def plan(*actions):
    return Plan.model_validate(dict(summary="排序", actions=list(actions)))


def test_swap_identity_data_history_save_render_export(w, tmp_path, monkeypatch):
    before = w.spec
    data = next(iter(w.datasets.values()))
    samples = data.samples.copy()
    def forbidden(*a, **kw):
        raise AssertionError("local order must not import or call AI")
    monkeypatch.setattr("wavelab.workbench.parse_file", forbidden)
    monkeypatch.setattr("wavelab.ai.assistant.Assistant.propose", forbidden)
    w.move_panel("panel_2", 1)
    assert ids(w) == ["panel_1", "panel_2"]
    assert w.spec.panels[1] is before.panels[0]
    assert w.spec.panels[1].series[0] is before.panels[0].series[0]
    assert w.spec.events == before.events
    assert next(iter(w.datasets.values())) is data
    np.testing.assert_array_equal(data.samples, samples)
    result = render_figure(w.spec, w.datasets)
    assert list(result.axes) == ids(w)
    assert result.axes["panel_1"].get_xlabel() == ""
    assert result.axes["panel_2"].get_xlabel()
    assert result.axes["panel_2"].get_ylim() == (0,20)
    assert len(result.axes["panel_2"].child_axes) == 1
    assert result.inset_axes["zoom"].get_position().bounds
    np.testing.assert_array_equal(result.inset_axes["zoom"].lines[0].get_ydata(), [1,2])
    assert len([l for l in result.axes["panel_1"].lines if l.get_gid()=="event_line"]) == 1
    assert len([l for l in result.axes["panel_2"].lines if l.get_gid()=="event_line"]) == 2
    first = result.lines[("panel_2",before.panels[0].series[0].channel_id)]
    assert (first.get_color(),first.get_linestyle(),first.get_linewidth()) == ("red","--",1.7)
    for fmt in ("pdf","svg","png"):
        assert export_figure(result,tmp_path/f"order.{fmt}").stat().st_size > 1000
    w.undo(); assert w.spec == before
    w.redo(); assert ids(w) == ["panel_1","panel_2"]
    path = w.save_project("order")
    other=Workbench(tmp_path/"other"); other.open_project(path)
    assert other.spec.panels == w.spec.panels


def test_five_arbitrary_moves_and_noop(w):
    for name in ("panel_3","panel_4","panel_5"):
        w.create_panel(name)
    originals = {p.id:p for p in w.spec.panels}
    expected = ids(w)
    for source, dest in [(0,4),(4,0),(2,1),(1,2),(3,0),(0,3)]:
        pid=expected.pop(source);expected.insert(dest,pid)
        w.move_panel(pid,dest)
        assert ids(w)==expected
        assert all(p is originals[p.id] for p in w.spec.panels)
    revision=w.revision
    w.move_panel(ids(w)[0],0)
    assert w.revision==revision


@pytest.mark.parametrize("pid,index",[("missing",0),("panel_1",-1),("panel_1",2),("panel_1",True),("panel_1",1.0)])
def test_invalid_move_atomic(w,pid,index):
    before=w.spec; revision=w.revision
    with pytest.raises(ValueError): w.move_panel(pid,index)
    assert w.spec is before and w.revision==revision


@pytest.mark.parametrize("order",[["panel_1"],["panel_1","panel_1"],["panel_1","unknown"]])
def test_invalid_permutation(w,order):
    before=w.spec
    with pytest.raises(ValueError): w.reorder_panels(order)
    assert w.spec is before


def test_drag_revision_and_binding(w):
    gesture=dict(panel_ids=["panel_1","panel_2"],revision=w.revision,binding=w.project_epoch)
    apply_order_gesture(w,gesture)
    assert ids(w)==gesture["panel_ids"]
    assert list(render_figure(w.spec,w.datasets).axes)==gesture["panel_ids"]
    with pytest.raises(ValueError): apply_order_gesture(w,gesture)
    with pytest.raises(ValueError): apply_order_gesture(w,dict(gesture,revision=w.revision,binding="other"))


def test_requested_split_case_and_ai_stale(w):
    original_five=w.spec.panels[1]
    original_six=w.spec.panels[0].series
    w.create_panel("panel_3")
    w.create_panel("panel_4")
    for j,s in enumerate(original_six[2:]):
        w.move_series("panel_2",s.channel_id,"panel_3" if j<2 else "panel_4")
    proposal=prepare(w,plan(dict(action="move_panel",panel_id="panel_1",target_index=3)))
    apply_proposal(w,proposal)
    assert ids(w)==["panel_2","panel_3","panel_4","panel_1"]
    assert [p.series for p in w.spec.panels[:3]] == [original_six[:2],original_six[2:4],original_six[4:]]
    roles={c.channel_id:c.physical_role for c in w.spec.datasets[0].channels}
    assert [roles[p.series[0].channel_id] for p in w.spec.panels[:3]] == ["A相上桥臂","B相上桥臂","C相上桥臂"]
    assert w.spec.panels[-1]==original_five
    with pytest.raises(ValueError,match="过期"): apply_proposal(w,proposal)
    w.undo();w.redo()
    with pytest.raises(ValueError,match="过期"): apply_proposal(w,proposal)


def test_ai_insert_three_between_two(w):
    actions=[dict(action="create_panel",panel_id=f"new_{i}",target_index=i) for i in range(1,4)]
    apply_proposal(w,prepare(w,plan(*actions)))
    assert ids(w)==["panel_2","new_1","new_2","new_3","panel_1"]
    schema=tool_definitions()["response_schema"]
    assert "move_panel" in schema["$defs"]["Action"]["properties"]["action"]["enum"]


@pytest.mark.parametrize("action",[
    dict(action="move_panel",panel_id="missing",target_index=0),
    dict(action="move_panel",panel_id="panel_1",target_index=2),
    dict(action="move_panel",panel_id="panel_1"),
    dict(action="move_panel",panel_id="panel_1",target_index=-1),
    dict(action="move_panel",panel_id="panel_1",target_index=True),
    dict(action="create_panel",panel_id="new",target_index=3),
    dict(action="update_panel",panel_id="panel_1",target_index=0),
])
def test_ai_invalid_order(w,action):
    before=w.spec
    with pytest.raises(ValueError): prepare(w,plan(action))
    assert w.spec is before


def test_gui_drag_only_insertion_history(w):
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=30)
    at.session_state["workbench"]=w
    at.run(); assert not at.exception
    assert not any(e.label in {"↑", "↓", "移动所选子图"} for e in at.button)
    assert not any(e.label == "移动到第几幅" for e in at.selectbox)
    apply_order_gesture(w,dict(panel_ids=["panel_1","panel_2"],revision=w.revision,binding=w.project_epoch))
    at.run()
    assert not at.exception and ids(w)==["panel_1","panel_2"]
    next(e for e in at.button if e.label=="撤销").click().run()
    assert ids(w)==["panel_2","panel_1"]
    next(e for e in at.button if e.label=="恢复").click().run()
    assert ids(w)==["panel_1","panel_2"]
    next(e for e in at.selectbox if e.label=="编辑子图").select("panel_1").run()
    next(e for e in at.selectbox if e.label=="新子图插入位置").select("在当前子图下方插入").run()
    next(e for e in at.button if e.label=="添加子图").click().run()
    assert not at.exception
    assert ids(w)==["panel_1","panel_3","panel_2"]


def test_manual_protocol_binding_fingerprint_and_stale_order(w):
    import json
    from wavelab.ai.manual import ManualExchange, protocol
    e=ManualExchange(); e.generate(w,"把 panel_1 放到最后")
    snap=e.snapshot
    raw=json.dumps(dict(request_id=snap.request_id, revision=snap.revision, fingerprint=snap.fingerprint,
                       plan=dict(summary="排序",actions=[dict(action="move_panel",panel_id="panel_2",target_index=1)])))
    assert "target_index" in protocol()["output_schema"]["$defs"]["Action"]["properties"]
    for bad in (dict(request_id="other"),dict(fingerprint="bad"),dict(revision=snap.revision+1)):
        document=json.loads(raw);document.update(bad)
        with pytest.raises(ValueError): e.validate(w,json.dumps(document))
    e.validate(w,raw)
    w.update(["page","font_size_pt"],10)
    before=w.spec
    with pytest.raises(ValueError,match="过期"): e.apply(w)
    assert w.spec is before


@pytest.mark.parametrize("index",[-1,3,True,1.5])
def test_invalid_insertion(w,index):
    before=w.spec
    with pytest.raises(ValueError):w.create_panel("new",index)
    assert w.spec is before


def test_planner_mock_generation_and_clarification(w):
    from wavelab.ai import Assistant, MockProvider
    assistant=Assistant()
    turn=assistant.propose(w,MockProvider([plan(dict(action="move_panel",panel_id="panel_2",target_index=1))]),"把第 1 幅放到最后",consent=True)
    assert turn.proposal.candidate.panels[-1].id=="panel_2"
    # This exercises the planner protocol, not real language understanding.
    clarification=Plan(summary="需要明确目标",clarification="请给出唯一子图 ID 或当前位置")
    before=w.spec
    turn=assistant.propose(w,MockProvider([clarification]),"把电压放到那里",consent=True)
    assert turn.proposal is None and w.spec is before

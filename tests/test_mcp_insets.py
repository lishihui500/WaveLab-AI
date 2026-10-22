from pathlib import Path
import json
import numpy as np
import pytest

from wavelab.workbench import Workbench
from wavelab.local_bridge import execute, status
from wavelab.commands.plot import Plan, build, prepare, apply_proposal
from wavelab.ai.manual import protocol, ManualExchange
from wavelab.render.engine import render_figure


@pytest.fixture
def work(tmp_path):
    w = Workbench(tmp_path)
    w.import_bytes(b"Domain,u,u\n1,1,3\n1.1,2,4\n1.2,3,2\n1.3,1,5\n1.4,2,3\n", "synthetic.csv")
    w.assign_channels("panel_1", [c.channel_id for c in w.spec.datasets[0].channels])
    w.create_panel("other")
    return w


def apply(w, actions):
    s = status(w, "gui")
    return execute(w, "gui", "apply_plot_actions", dict(expected_revision=s["revision"],
        expected_fingerprint=s["fingerprint"], expected_project_epoch=s["project_epoch"],
        user_request="局部图开发测试", actions=actions))


def create(iid="zoom", **changes):
    return dict(action="create_inset", panel_id="panel_1", inset_id=iid,
                changes=dict(xlim_s=[1.1, 1.3], **changes))


def test_lifecycle_patch_history_and_samples(work):
    original = work.spec
    arrays = {k: v.samples.copy() for k, v in work.data.items()}
    apply(work, [create()])
    first = work.spec
    apply(work, [dict(action="update_inset", panel_id="panel_1", inset_id="zoom",
                     changes=dict(bounds=[.05, .5, .4, .4], ylim=[0., 6.], show_connectors=False))])
    inset = work.spec.panels[0].insets[0]
    assert inset.xlim_s == (1.1, 1.3) and inset.bounds == (.05, .5, .4, .4)
    assert not inset.show_connectors and inset.show_region
    assert work.spec.panels[0].series == original.panels[0].series
    apply(work, [dict(action="update_inset", panel_id="panel_1", inset_id="zoom", changes=dict(ylim=None))])
    assert work.spec.panels[0].insets[0].ylim is None
    apply(work, [dict(action="remove_inset", panel_id="panel_1", inset_id="zoom")])
    assert not work.spec.panels[0].insets
    apply(work, [dict(action="undo")])
    assert len(work.spec.panels[0].insets) == 1
    apply(work, [dict(action="redo")])
    assert not work.spec.panels[0].insets
    for k, source in arrays.items():
        np.testing.assert_array_equal(work.data[k].samples, source)


@pytest.mark.parametrize("action", [
    dict(action="create_inset", panel_id="bad", inset_id="zoom", changes=dict(xlim_s=[1., 1.2])),
    dict(action="create_inset", panel_id="panel_1", changes=dict(xlim_s=[1., 1.2])),
    dict(action="create_inset", panel_id="panel_1", inset_id="zoom"),
    create(bounds=[.9, .5, .4, .4]),
    create(channel_ids=["unknown:col_1"]),
    dict(action="create_inset", panel_id="panel_1", inset_id="zoom", changes=dict(xlim_s=[9., 10.])),
    dict(action="create_inset", panel_id="panel_1", inset_id="zoom", changes=dict(xlim_s=[1.3, 1.1])),
    create(ylim=[2., 1.]),
    create(show_region="false"),
    create(bounds=[0., 0., float("nan"), .4]),
    dict(action="update_inset", panel_id="panel_1", inset_id="missing", changes=dict(show_region=False)),
    dict(action="remove_inset", panel_id="panel_1", inset_id="missing"),
    dict(action="move_panel", panel_id="panel_1", target_index=0, inset_id="unexpected"),
])
def test_invalid_batch_rolls_back(work, action):
    before, revision, depth = work.spec, work.revision, len(work.undo_stack)
    with pytest.raises((ValueError, KeyError)):
        apply(work, [dict(action="update_panel", panel_id="panel_1", changes=dict(title_i18n=dict(zh="待回滚"))), action])
    assert (work.spec, work.revision, len(work.undo_stack)) == (before, revision, depth)


def test_parent_channels_duplicate_ids_and_visibility(work):
    cid = work.spec.panels[0].series[0].channel_id
    with pytest.raises(ValueError, match="所属主图"):
        apply(work, [dict(action="create_inset", panel_id="other", inset_id="zoom", changes=dict(xlim_s=[1.1,1.3], channel_ids=[cid]))])
    apply(work, [create()])
    with pytest.raises(ValueError, match="唯一"):
        apply(work, [create()])
    with pytest.raises(ValueError, match="不存在局部图"):
        apply(work, [dict(action="remove_inset", panel_id="other", inset_id="zoom")])
    work.update(["panels",0,"series",0,"visible"], False)
    with pytest.raises(ValueError, match="有效样本"):
        apply(work, [create("hidden", channel_ids=[cid])])


def test_multiple_insets_batch_and_styles_render_save(work, tmp_path):
    cid = work.spec.panels[0].series[0].channel_id
    work.update(["panels",0,"series",0,"color"], "#D55E00")
    work.update(["panels",0,"series",0,"linestyle"], "--")
    before, depth = work.spec, len(work.undo_stack)
    apply(work, [create("one", channel_ids=[cid], bounds=[.05,.5,.4,.4]),
                 create("two", bounds=[.55,.1,.4,.4])])
    assert len(work.undo_stack) == depth + 1
    result = render_figure(work.spec, work.datasets)
    try:
        children = result.figure.axes[0].child_axes
        assert len(children) == 2
        assert children[0].lines[0].get_color() == "#D55E00"
        assert children[0].lines[0].get_linestyle() == "--"
        assert len(children[0].lines[0].get_xdata()) == 3
    finally:
        import matplotlib.pyplot as plt
        plt.close(result.figure)
    path = work.save_project("mcp_insets")
    reopened = Workbench(tmp_path / "reopened")
    reopened.open_project(path)
    assert reopened.spec.panels == work.spec.panels
    work.undo()
    assert work.spec == before


def test_relative_ms_keeps_physical_seconds_and_stale_guard(work):
    work.update(["events"], [dict(time_s=1.2, label="Event", confirmation_source="fixture")])
    apply(work, [dict(action="set_time_axis", changes=dict(mode="relative", unit="ms", event_time_s=1.2)), create()])
    assert work.spec.panels[0].insets[0].xlim_s == (1.1, 1.3)
    plan = Plan.model_validate(dict(summary="zoom", actions=[dict(action="update_inset", panel_id="panel_1", inset_id="zoom", changes=dict(show_region=False))]))
    proposal = prepare(work, plan)
    work.move_panel("other", 0)
    with pytest.raises(ValueError, match="过期"):
        apply_proposal(work, proposal)
    apply(work, [dict(action="set_time_axis", changes=dict(mode="absolute", unit="s"))])
    assert work.spec.panels[1].insets[0].xlim_s == (1.1, 1.3)


def test_schema_and_manual_json_share_inset_actions(work):
    p = protocol()
    assert "xlim_s" in p["patch_schema_by_action"]["create_inset"]
    assert p["targets_by_action"]["update_inset"] == ["inset_id", "panel_id"]
    exchange = ManualExchange()
    exchange.generate(work, "添加局部图，绝对时间 1.1 s 到 1.3 s")
    snapshot = exchange.snapshot
    raw = json.dumps(dict(request_id=snapshot.request_id, revision=snapshot.revision,
        fingerprint=snapshot.fingerprint, plan=dict(summary="添加局部图", actions=[create()])))
    exchange.validate(work, raw)
    exchange.apply(work)
    assert work.spec.panels[0].insets[0].id == "zoom"

import numpy as np
import pytest

from wavelab.workbench import Workbench
from wavelab.local_bridge import execute, status
from wavelab.render.engine import render_figure
from wavelab.ai.manual import protocol


def apply(w, actions):
    state = status(w, "test")
    return execute(w, "test", "apply_plot_actions", dict(
        expected_revision=state["revision"], expected_project_epoch=state["project_epoch"],
        expected_fingerprint=state["fingerprint"], actions=actions, user_request="Trip 分层轨道"))


def work(tmp_path, bad=False):
    w = Workbench(tmp_path)
    w.import_bytes(("Domain,Trip1a,Trip1b,Trip1c\n0,0,0,0\n0.1,1,0,0\n"
                    + ("0.2,2,1,0\n" if bad else "0.2,1,1,0\n")
                    + "0.3,0,1,0\n").encode(), "digital.csv")
    w.assign_channels("panel_1", [c.channel_id for c in w.spec.datasets[0].channels])
    return w


def test_tracks_insets_history_and_reopen(tmp_path):
    w = work(tmp_path)
    original = w.spec
    samples = {key: value.samples.copy() for key, value in w.data.items()}
    result = apply(w, [dict(action="update_panel", panel_id="panel_1", changes={"plot_mode": "digital_tracks"}),
                       dict(action="create_inset", panel_id="panel_1", inset_id="zoom",
                            changes={"xlim_s": [.05, .25]})])
    assert result["result"]["render_success"]
    drawing = render_figure(w.spec, w.data)
    assert not drawing.warnings
    assert drawing.axes["panel_1"].get_ylabel() == "逻辑状态"
    for i, series in enumerate(w.spec.panels[0].series):
        line = drawing.lines[("panel_1", series.channel_id)]
        assert line.get_drawstyle() == "steps-post"
        np.testing.assert_array_equal(line.get_xdata(), [0, .1, .2, .3])
        np.testing.assert_array_equal(line.get_ydata(), next(iter(w.data.values())).values(series.channel_id) + 2*(2-i))
        inset_line = drawing.inset_axes["zoom"].lines[i]
        assert inset_line.get_drawstyle() == "steps-post"
        assert inset_line.get_xdata()[0] == 0  # preceding held state
    assert "Trip1a" in drawing.axes["panel_1"].get_yticklabels()[0].get_text()
    final = w.spec
    apply(w, [dict(action="undo")]); assert w.spec == original
    apply(w, [dict(action="redo")]); assert w.spec == final
    path = w.save_project("tracks")
    fresh = Workbench(tmp_path); fresh.open_project(path)
    assert fresh.spec.panels[0].plot_mode == "digital_tracks"
    for key, values in samples.items():
        np.testing.assert_array_equal(fresh.data[key].samples, values)
        np.testing.assert_array_equal(w.data[key].samples, values)


def test_nonbinary_batch_rejected_atomically(tmp_path):
    w = work(tmp_path, bad=True)
    before, revision = w.spec, w.revision
    with pytest.raises(ValueError, match="binary"):
        apply(w, [dict(action="update_panel", panel_id="panel_1", changes={"plot_mode": "digital_tracks"})])
    assert w.spec == before and w.revision == revision
    with pytest.raises(ValueError, match="binary"):
        w.update(["panels", 0, "plot_mode"], "digital_tracks")
    assert w.spec == before and w.revision == revision


def test_schema_and_legacy_default(tmp_path):
    w = work(tmp_path)
    assert w.spec.panels[0].plot_mode == "analog"
    assert "plot_mode" in protocol()["patch_schema_by_action"]["update_panel"]

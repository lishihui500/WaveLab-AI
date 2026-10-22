import json
from concurrent.futures import ThreadPoolExecutor
from time import sleep, monotonic
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest
from wavelab.local_bridge import Bridge, execute, status
from wavelab.mcp_server import rpc, create_server
from wavelab.workbench import Workbench


@pytest.fixture
def work(tmp_path):
    w = Workbench(tmp_path)
    w.import_bytes(b"Domain,u,u\n0,1,2\n1,3,4\n", "synthetic.csv")
    w.create_panel("second")
    w.create_panel("third")
    w.assign_channels("panel_1", [c.channel_id for c in w.spec.datasets[0].channels])
    return w


def request(w, actions=None):
    s = status(w, "gui")
    return dict(expected_revision=s["revision"], expected_fingerprint=s["fingerprint"],
                expected_project_epoch=s["project_epoch"], user_request="把第三幅移到第一幅",
                actions=actions or [dict(action="move_panel", panel_id="third", target_index=0)])


def test_reorder_undo_redo_and_conflict(work):
    before = work.spec
    old = request(work)
    result = execute(work, "gui", "apply_plot_actions", old)
    assert result["result"]["samples_unchanged"]
    assert [p.id for p in work.spec.panels] == ["third", "panel_1", "second"]
    assert execute(work, "gui", "apply_plot_actions", old)["error"] == "version_conflict"
    execute(work, "gui", "apply_plot_actions", request(work, [dict(action="undo")]))
    assert work.spec == before
    execute(work, "gui", "apply_plot_actions", request(work, [dict(action="redo")]))
    assert work.spec.panels[0].id == "third"


def test_batch_rollback_and_one_undo(work):
    before, revision, undo = work.spec, work.revision, len(work.undo_stack)
    actions = [dict(action="create_panel", panel_id="new", target_index=1),
               dict(action="move_series", panel_id="panel_1", target_panel_id="missing", channel_id=work.spec.panels[0].series[0].channel_id)]
    with pytest.raises(ValueError):
        execute(work, "gui", "apply_plot_actions", request(work, actions))
    assert (work.spec, work.revision, len(work.undo_stack)) == (before, revision, undo)
    actions[1]["target_panel_id"] = "new"
    execute(work, "gui", "apply_plot_actions", request(work, actions))
    assert len(work.undo_stack) == undo + 1
    work.undo()
    assert work.spec == before


def test_metadata_and_missing_project(work, tmp_path):
    context = execute(work, "gui", "get_figure_context", {})
    raw = json.dumps(context)
    assert "samples" not in raw and "source_path" not in raw and "synthetic.csv" not in raw
    cid = work.spec.datasets[0].channels[0].channel_id
    result = execute(work, "gui", "get_channel_metadata", dict(channel_id=cid))
    assert result["placements"][0]["panel_id"] == "panel_1"
    assert execute(work, "gui", "get_channel_metadata", dict(channel_id="invalid"))["error"] == "unknown_channel"
    assert execute(Workbench(tmp_path), "gui", "get_figure_context", {})["error"] == "no_project"


def pump(bridge, work, futures):
    deadline = monotonic() + 20
    while not all(f.done() for f in futures):
        bridge.drain("gui", work)
        assert monotonic() < deadline
        sleep(.01)
    return [f.result() for f in futures]


def test_http_and_concurrent_writes(work, tmp_path):
    bridge = Bridge(tmp_path / "runtime")
    try:
        bridge.attach("gui")
        assert rpc("list_sessions", runtime_dir=tmp_path / "runtime") == {"sessions": ["gui"]}
        assert rpc("get_figure_context", runtime_dir=tmp_path / "runtime")["error"] == "session_required"
        old = request(work)
        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(rpc, "apply_plot_actions", old, "gui", tmp_path / "runtime") for _ in range(2)]
            results = pump(bridge, work, futures)
        assert sum("result" in r for r in results) == 1
        assert sum(r.get("error") == "version_conflict" for r in results) == 1
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(f"http://127.0.0.1:{bridge.server.server_port}/rpc", b"{}"))
        assert exc.value.code == 403
        bridge.attach("other")
        assert len(rpc("list_sessions", runtime_dir=tmp_path / "runtime")["sessions"]) == 2
        bridge.sessions["gui"].seen -= 20
        assert bridge.request("get_figure_context", {}, "gui")["error"] == "session_required"
    finally:
        bridge.close()
    assert rpc("get_figure_context", session_id="gui", runtime_dir=tmp_path / "runtime")["error"] == "not_running"


def test_cancelled_request_does_not_execute_later(work, tmp_path):
    bridge = Bridge(tmp_path / "runtime")
    try:
        bridge.attach("gui")
        revision = work.revision
        assert bridge.request("apply_plot_actions", request(work), "gui", timeout=.01)["error"] == "gui_unresponsive"
        bridge.drain("gui", work)
        assert work.revision == revision
    finally:
        bridge.close()


def test_project_epoch_and_invalid_actions(work):
    old = request(work)
    work.project_epoch = "reopened"
    assert execute(work, "gui", "apply_plot_actions", old)["error"] == "version_conflict"
    for action in [dict(action="move_panel", panel_id="bad", target_index=0),
                   dict(action="add_series", panel_id="panel_1", channel_id="bad"),
                   dict(action="shell", changes={"code": "anything"})]:
        with pytest.raises((ValueError, KeyError)):
            execute(work, "gui", "apply_plot_actions", request(work, [action]))


def test_mcp_schema():
    import asyncio
    names = asyncio.run(create_server().list_tools())
    assert {t.name for t in names} == {"get_wavelab_status", "get_figure_context", "get_channel_metadata", "apply_plot_actions", "get_plot_action_schema", "get_quantity_presets", "get_edit_target", "save_project"}


def test_stage_b_actions_and_save_reopen(work, tmp_path):
    import numpy as np
    original_samples = {k: v.samples.copy() for k, v in work.data.items()}
    cid = work.spec.panels[0].series[0].channel_id
    actions = [dict(action="update_series", panel_id="panel_1", channel_id=cid, changes=dict(color="#0072B2", linestyle="--")),
               dict(action="move_series", panel_id="panel_1", channel_id=cid, target_panel_id="second"),
               dict(action="update_panel", panel_id="second", changes=dict(ylim=[-1., 5.], title_i18n=dict(zh="幅值", en="Value"))),
               dict(action="set_legend", changes=dict(columns=2)),
               dict(action="set_time_axis", changes=dict(xlim=[0., .5])),
               dict(action="upsert_event", evidence_quote="事件在 0.2 s", changes=dict(time_s=.2, label="Event")),
               dict(action="remove_panel", panel_id="third")]
    payload = request(work, actions)
    payload["user_request"] = "事件在 0.2 s；移动曲线并调整坐标轴和图例"
    result = execute(work, "gui", "apply_plot_actions", payload)
    assert "changes" not in result["result"] and result["result"]["change_count"] > 0
    series = work.spec.panels[1].series[0]
    assert (series.color, series.linestyle) == ("#0072B2", "--")
    expected = work.spec.panels
    project = work.save_project("MCP_validation")
    fresh = Workbench(tmp_path / "fresh")
    fresh.open_project(project)
    assert fresh.spec.panels == expected
    assert fresh.spec.events == work.spec.events
    for key, samples in original_samples.items():
        np.testing.assert_array_equal(work.data[key].samples, samples)
        np.testing.assert_array_equal(fresh.data[key].samples, samples)


def test_gui_remote_sort_then_one_click_undo(tmp_path):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    from wavelab.local_bridge import get_bridge
    root = Path(__file__).resolve().parents[1]
    at = AppTest.from_file(root / "app.py", default_timeout=30)
    at.session_state["workbench"] = Workbench(tmp_path)
    at.run()
    next(e for e in at.text_area if e.label == "含 Domain 表头的数据").input("Domain,u\n0,1\n1,2").run()
    next(e for e in at.button if e.label == "导入粘贴文本").click().run()
    w = at.session_state["workbench"]
    w.create_panel("second")
    w.create_panel("third")
    at.run()
    before = w.spec
    bridge = get_bridge(root / ".wavelab" / "runtime")
    sid = at.session_state["mcp_session_id"]
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(bridge.request, "apply_plot_actions", request(w), sid)
        deadline = monotonic() + 5
        while bridge.sessions[sid].queue.empty():
            assert monotonic() < deadline
            sleep(.01)
        at.run()
        assert "result" in pending.result()
    assert w.spec.panels[0].id == "third"
    next(e for e in at.button if e.label == "撤销").click().run()
    assert not at.exception
    assert w.spec == before
    assert len(w.spec.datasets) == 1


def test_three_phase_split_preserves_styles(tmp_path):
    w = Workbench(tmp_path)
    did = w.import_bytes(b"Domain,u,u,u,u,u,u\n0,1,2,3,4,5,6\n1,2,3,4,5,6,7\n", "synthetic.csv")
    # Synthetic fixture explicitly defines A upper/lower, B upper/lower, C upper/lower.
    w.map_channels(did, "u", "six_arms", "synthetic fixture defines six-arm order", "kV")
    channels = w.spec.datasets[0].channels
    w.assign_channels("panel_1", [c.channel_id for c in channels])
    w.create_panel("last")
    for index, series in enumerate(w.spec.panels[0].series):
        w.update(["panels", 0, "series", index, "color"], "#0072B2" if index % 2 == 0 else "#D55E00")
        w.update(["panels", 0, "series", index, "linestyle"], "-" if index % 2 == 0 else "--")
    originals = {s.channel_id: s for s in w.spec.panels[0].series}
    before, depth = w.spec, len(w.undo_stack)
    actions = []
    for index, phase in enumerate("ABC", 1):
        pid = "phase_" + phase
        actions.append(dict(action="create_panel", panel_id=pid, target_index=index))
        for channel in channels[(index-1)*2:index*2]:
            actions.append(dict(action="move_series", panel_id="panel_1", channel_id=channel.channel_id, target_panel_id=pid))
    execute(w, "gui", "apply_plot_actions", request(w, actions))
    assert [p.id for p in w.spec.panels] == ["panel_1", "phase_A", "phase_B", "phase_C", "last"]
    assert {s.channel_id: s for p in w.spec.panels for s in p.series} == originals
    assert len(w.undo_stack) == depth + 1
    w.undo()
    assert w.spec == before

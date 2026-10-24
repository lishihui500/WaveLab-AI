"""Routing/coverage contract tests; synthetic data stays inside pytest temp roots."""
from concurrent.futures import ThreadPoolExecutor
import json
from time import monotonic, sleep
from urllib.request import Request, urlopen

import pytest
import numpy as np
from wavelab.local_bridge import Bridge, execute, status
from wavelab.mcp_protocol import identity
from wavelab.mcp_server import rpc, _routes
from wavelab.workbench import Workbench


@pytest.fixture
def work(tmp_path):
    w = Workbench(tmp_path / "work")
    w.import_bytes(b"Domain,u\n0,1\n0.001,2\n0.01,3\n0.011,4\n", "fixture.csv")
    w.assign_channels("panel_1", [w.spec.datasets[0].channels[0].channel_id])
    return w


def fetch(bridge, w, directory, method="get_figure_context", params=None):
    with ThreadPoolExecutor(1) as pool:
        f = pool.submit(rpc, method, params, "gui", directory)
        deadline = monotonic() + 10
        while not f.done():
            bridge.drain("gui", w)
            assert monotonic() < deadline
            sleep(.002)
        return f.result()


def test_five_sessions_same_names_target_switch_epoch_expiry(work, tmp_path):
    b = Bridge(tmp_path / "runtime")
    try:
        for sid in ["gui", "b", "c", "d", "e"]:
            b.attach(sid)
        assert b.request("get_edit_target", {})["error"] == "target_unbound"
        b.bind_target("gui", work)
        assert rpc("get_edit_target", runtime_dir=tmp_path / "runtime")["target"]["session_id"] == "gui"
        b.bind_target("b", work)  # same work/name, distinct session identity
        assert b.request("get_edit_target", {})["target"]["session_id"] == "b"
        b.bind_target("gui", work)
        work.project_epoch = "another-project"
        b.drain("gui", work)
        assert b.request("get_edit_target", {})["error"] == "target_unbound"
        b.bind_target("gui", work)
        b.sessions["gui"].seen -= 20
        assert b.request("get_edit_target", {})["error"] == "target_offline"
        b.attach("gui")
        assert b.request("get_edit_target", {})["target"]["session_id"] == "gui"
    finally:
        b.close()


def test_unique_across_endpoints_and_restart(work, tmp_path):
    directory = tmp_path / "runtime"
    a, b = Bridge(directory), Bridge(directory)
    try:
        a.attach("a"); b.attach("gui")
        a.bind_target("a", work)
        b.bind_target("gui", work)
        assert a.request("get_edit_target", {})["error"] == "target_unbound"
        assert rpc("get_edit_target", runtime_dir=directory)["target"]["session_id"] == "gui"
        assert "context" in fetch(b, work, directory)
    finally:
        a.close(); b.close()
    c = Bridge(directory)
    try:
        c.attach("gui")
        assert c.request("get_edit_target", {})["error"] == "target_unbound"
        assert "context" in fetch(c, work, directory)
    finally:
        c.close()


def test_warm_route_no_discovery_and_protocol_reject(work, tmp_path):
    directory = tmp_path / "runtime"
    b = Bridge(directory)
    try:
        b.attach("gui")
        cold = fetch(b, work, directory)
        warm = fetch(b, work, directory)
        assert "endpoint_discovery_ms" in cold["diagnostics"]["stages_ms"]
        assert "endpoint_discovery_ms" not in warm["diagnostics"]["stages_ms"]
        old = status(work, "gui")
        url = f"http://127.0.0.1:{b.server.server_port}/rpc"
        for protocol in [None, dict(identity(), schema_hash="stale")]:
            request = Request(url, json.dumps(dict(method="apply_plot_actions", session_id="gui", protocol=protocol)).encode(),
                              {"Authorization": "Bearer " + b.token})
            with urlopen(request) as response:
                assert json.load(response)["error"] == "protocol_mismatch"
        assert status(work, "gui") == old
    finally:
        b.close()


@pytest.mark.parametrize("window", [[1.295, 1.320], [.003, .008]])
def test_window_has_no_actual_points(work, window):
    old = status(work, "gui")
    result = execute(work, "gui", "get_figure_context", dict(window_s=window))
    assert result["coverage"]["channels"][0]["window_finite_count"] == 0
    assert not result["coverage"]["panels"][0]["drawable"]
    assert status(work, "gui") == old


def test_nonfinite_window_and_readback(work):
    # Inject a read-only missing-value fixture without altering protected project inputs.
    data = next(iter(work.data.values()))
    values = data.samples.copy()
    values[1, 1] = np.nan
    values.flags.writeable = False
    object.__setattr__(data, "samples", values)
    summary = execute(work, "gui", "get_figure_context", dict(window_s=[.0009, .0011]))
    assert summary["coverage"]["channels"][0]["finite_count"] == 3
    assert not summary["coverage"]["panels"][0]["drawable"]
    with pytest.raises(ValueError):
        execute(work, "gui", "get_figure_context", dict(window_s=[2, 1]))


def save_identity(w):
    s = status(w, "gui")
    return dict(expected_revision=s["revision"], expected_project_epoch=s["project_epoch"], expected_fingerprint=s["fingerprint"])


def test_save_current_only_success_failure_and_conflict(work, monkeypatch):
    assert execute(work, "gui", "save_project", save_identity(work))["error"] == "save_requires_gui"
    work.save_project("existing")
    payload = save_identity(work)
    result = execute(work, "gui", "save_project", payload)
    assert result["saved"] and result["saved_revision"] == work.revision
    old = work.spec, work.revision, result["fingerprint"]
    def fail(*args):
        raise OSError("disk failure")
    monkeypatch.setattr(work, "save_project", fail)
    result = execute(work, "gui", "save_project", payload)
    assert result["error"] == "save_failed" and not result["saved"] and result["saved_revision"] is None
    assert (work.spec, work.revision, result["fingerprint"]) == old
    payload["expected_revision"] += 1
    assert execute(work, "gui", "save_project", payload)["error"] == "version_conflict"


def test_rejected_batch_and_successful_readback(work):
    from wavelab.commands.plot import sample_hashes
    before = status(work, "gui"), work.spec, sample_hashes(work)
    cid = work.spec.panels[0].series[0].channel_id
    actions = [dict(action="update_series", panel_id="panel_1", channel_id=cid, changes=dict(color="#FF0000")),
               dict(action="remove_panel", panel_id="missing")]
    payload = dict(save_identity(work), actions=actions, user_request="red")
    with pytest.raises(ValueError):
        execute(work, "gui", "apply_plot_actions", payload)
    assert (status(work, "gui"), work.spec, sample_hashes(work)) == before
    payload["actions"] = actions[:1]
    result = execute(work, "gui", "apply_plot_actions", payload)
    readback = execute(work, "gui", "get_figure_context", {})
    assert result["fingerprint"] == readback["fingerprint"]
    assert readback["context"]["panels"][0]["series"][0]["color"] == "#FF0000"
    assert sample_hashes(work) == before[2]


def test_gui_bind_and_unbind_uses_isolated_bridge(work, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from pathlib import Path
    import wavelab.local_bridge as module
    b = Bridge(tmp_path / "isolated-runtime")
    monkeypatch.setattr(module, "get_bridge", lambda directory: b)
    try:
        at = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30)
        at.session_state["workbench"] = work
        at.run()
        assistant = next(x for x in at.expander if x.label == "AI 科研绘图助手")
        assert any(x.label == "设为 Codex 编辑目标" for x in assistant.button)
        assert not at.session_state.get("ai_enabled", False)
        assert not any("阶段 3C" in x.value for x in at.caption)
        next(x for x in at.button if x.label == "设为 Codex 编辑目标").click().run()
        assert not at.exception
        assert b.request("get_edit_target", {})["target"]["session_id"] == at.session_state["mcp_session_id"]
        next(x for x in at.button if x.label == "解除 Codex 编辑目标").click().run()
        assert b.request("get_edit_target", {})["error"] == "target_unbound"
        assert not at.exception
    finally:
        b.close()


def test_old_gui_without_protocol_is_rejected(tmp_path, monkeypatch):
    from io import BytesIO
    import wavelab.mcp_server as module
    directory = tmp_path / "runtime"
    directory.mkdir()
    (directory / "old.json").write_text(json.dumps(dict(port=12345, token="test-only")), encoding="utf-8")
    class OldTransport:
        def open(self, *args, **kwargs):
            return BytesIO(json.dumps(dict(sessions=["gui"])).encode())
    monkeypatch.setattr(module, "build_opener", lambda *args: OldTransport())
    assert rpc("get_figure_context", session_id="gui", runtime_dir=directory)["error"] == "protocol_mismatch"


def test_invalid_http_payload_has_safe_failure_record(tmp_path):
    b = Bridge(tmp_path / "runtime")
    try:
        request = Request(f"http://127.0.0.1:{b.server.server_port}/rpc", b"not-json", {"Authorization": "Bearer " + b.token})
        with urlopen(request) as response:
            result = json.load(response)
        assert result["error"] == "invalid_request"
        assert not result["diagnostics"]["success"]
        assert b.token not in json.dumps(list(b.performance_records))
    finally:
        b.close()

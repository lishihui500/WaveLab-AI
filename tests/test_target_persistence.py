"""Consent/lease separation, using only synthetic projects under pytest roots."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import sys
from time import monotonic, sleep

import pytest

from wavelab.local_bridge import Bridge, status
from wavelab.mcp_server import rpc, _routes
from wavelab.workbench import Workbench


@pytest.fixture
def work(tmp_path):
    w = Workbench(tmp_path / "work")
    w.import_bytes(b"Domain,u\n0,1\n1,2\n", "synthetic.csv")
    w.assign_channels("panel_1", [w.spec.datasets[0].channels[0].channel_id])
    w.save_project("target")
    return w


def payload(w):
    s = status(w, "old")
    return dict(expected_revision=s["revision"], expected_fingerprint=s["fingerprint"],
                expected_project_epoch=s["project_epoch"], user_request="red",
                actions=[dict(action="update_series", panel_id="panel_1",
                              channel_id=w.spec.panels[0].series[0].channel_id,
                              changes=dict(color="#FF0000"))])


def pumped(b, w, method, params, sid, directory):
    with ThreadPoolExecutor(1) as pool:
        result = pool.submit(rpc, method, params, sid, directory)
        deadline = monotonic() + 10
        while not result.done():
            b.drain(sid, w)
            assert monotonic() < deadline
            sleep(.002)
        return result.result()


def test_offline_keeps_consent_cold_and_warm_routes_reject_write(work, tmp_path):
    directory = tmp_path / "runtime"
    b = Bridge(directory)
    try:
        b.bind_target("old", work, persistent=True)
        original = b.target_file.read_bytes()
        before = status(work, "old")
        for _ in range(3):
            assert rpc("get_edit_target", runtime_dir=directory)["online"]
        b.sessions["old"].seen -= 20
        result = rpc("get_edit_target", runtime_dir=directory)
        assert result["error"] == "target_offline" and not result["online"]
        assert result["persistent"]
        for warm in (True, False):
            if not warm:
                _routes.clear()
            assert rpc("apply_plot_actions", payload(work), "old", directory)["error"] == "target_offline"
            assert b.sessions["old"].queue.empty()
        assert b.target_file.read_bytes() == original
        assert status(work, "old") == before
        b.drain("old", work)
        assert rpc("get_edit_target", runtime_dir=directory)["target"]["session_id"] == "old"
        assert status(work, "old") == before
    finally:
        b.close()


def test_reload_updates_session_epoch_and_rejects_old_transaction(work, tmp_path):
    directory = tmp_path / "runtime"
    b = Bridge(directory)
    try:
        b.bind_target("old", work, persistent=True)
        stale = payload(work)
        b.sessions["old"].seen -= 20
        fresh = Workbench(work.root)
        fresh.open_project(work.project_path)
        b.drain("new", fresh)
        target = rpc("get_edit_target", runtime_dir=directory)["target"]
        assert target == dict(session_id="new", project_epoch=fresh.project_epoch)
        before = status(fresh, "new")
        result = pumped(b, fresh, "apply_plot_actions", stale, "new", directory)
        assert result["error"] == "version_conflict"
        assert status(fresh, "new") == before
        result = pumped(b, fresh, "apply_plot_actions", payload(fresh), "new", directory)
        assert result["result"]["samples_unchanged"]
        assert fresh.spec.panels[0].series[0].color == "#FF0000"
    finally:
        b.close()


def test_restart_requires_exact_project_and_explicit_revoke_survives_restart(work, tmp_path):
    directory = tmp_path / "runtime"
    b = Bridge(directory)
    b.bind_target("old", work, persistent=True)
    binding = b.target_store.read()["binding_id"]
    b.close()
    assert rpc("get_edit_target", runtime_dir=directory)["error"] == "target_offline"
    c = Bridge(directory)
    try:
        fresh = Workbench(work.root)
        # Same display name and same content in another location cannot restore.
        copy = tmp_path / "copy" / "target"
        shutil.copytree(work.project_path.parent, copy)
        fresh.open_project(copy / "project.json")
        c.drain("new", fresh)
        assert rpc("get_edit_target", runtime_dir=directory)["error"] == "target_offline"
        fresh.open_project(work.project_path)
        c.drain("new", fresh)
        assert rpc("get_edit_target", runtime_dir=directory)["target"]["session_id"] == "new"
        assert c.target_store.read()["binding_id"] == binding
        c.unbind_target("new")
        assert not c.target_file.exists()
        assert c.request("apply_plot_actions", payload(fresh), "new")["error"] == "target_changed"
        c.drain("new", fresh)
        assert rpc("get_edit_target", runtime_dir=directory)["error"] == "target_unbound"
    finally:
        c.close()
    d = Bridge(directory)
    try:
        d.drain("again", work)
        assert rpc("get_edit_target", runtime_dir=directory)["error"] == "target_unbound"
    finally:
        d.close()


def test_same_endpoint_reopen_and_project_switch_revokes(work, tmp_path):
    b = Bridge(tmp_path / "runtime")
    try:
        b.bind_target("gui", work, persistent=True)
        old_epoch = work.project_epoch
        work.open_project(work.project_path)
        b.drain("gui", work)
        assert b.request("get_edit_target", {})["target"]["project_epoch"] != old_epoch
        other = work.save_project("other")
        work.open_project(other)
        b.drain("gui", work)
        assert b.request("get_edit_target", {})["error"] == "target_unbound"
        work.open_project(work.root / "projects" / "target" / "project.json")
        b.drain("gui", work)
        assert b.request("get_edit_target", {})["error"] == "target_unbound"
    finally:
        b.close()


def test_identity_failure_revokes_and_unnamed_cannot_persist(work, tmp_path):
    b = Bridge(tmp_path / "runtime")
    try:
        b.bind_target("gui", work, persistent=True)
        work.import_bytes(b"Domain,v\n0,5\n1,6\n", "second.csv")
        b.drain("gui", work)
        assert not b.target_file.exists()
        with pytest.raises(ValueError, match="保存"):
            b.bind_target("gui", work, persistent=True)
        unnamed = Workbench(tmp_path / "unnamed")
        unnamed.import_bytes(b"Domain,u\n0,1\n1,2\n", "synthetic.csv")
        with pytest.raises(ValueError, match="保存"):
            b.bind_target("other", unnamed, persistent=True)
    finally:
        b.close()


def test_duplicate_sessions_and_endpoints_cannot_steal_live_selection(work, tmp_path):
    directory = tmp_path / "runtime"
    a, b = Bridge(directory), Bridge(directory)
    try:
        a.bind_target("selected", work, persistent=True)
        a.drain("duplicate", work)
        b.drain("other-process", work)
        assert rpc("get_edit_target", runtime_dir=directory)["target"]["session_id"] == "selected"
        # Explicit selection may switch; old pages cannot revoke or resurrect it.
        b.bind_target("other-process", work, persistent=True)
        a.unbind_target("selected")
        a.drain("selected", work)
        assert rpc("get_edit_target", runtime_dir=directory)["target"]["session_id"] == "other-process"
        b.unbind_target("other-process")
        a.drain("selected", work)
        assert rpc("get_edit_target", runtime_dir=directory)["error"] == "target_unbound"
    finally:
        a.close()
        b.close()


@pytest.mark.parametrize("change", ["unbind", "switch"])
def test_queued_command_rejected_after_selection_changes(work, tmp_path, change):
    b = Bridge(tmp_path / "runtime")
    try:
        b.bind_target("gui", work, persistent=True)
        before = status(work, "gui")
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(b.request, "apply_plot_actions", payload(work), "gui", 2)
            deadline = monotonic() + 1
            while b.sessions["gui"].queue.empty():
                assert monotonic() < deadline
                sleep(.002)
            if change == "unbind":
                b.unbind_target("gui")
            else:
                b.bind_target("other", work)
            b.drain("gui", work)
            assert future.result()["error"] == "target_changed"
        assert status(work, "gui") == before
    finally:
        b.close()


def test_store_compare_and_swap_cannot_restore_revoked_binding(work, tmp_path):
    b = Bridge(tmp_path / "runtime")
    try:
        b.bind_target("gui", work, persistent=True)
        stale = b.target_store.read()
        b.unbind_target("gui")
        assert not b.target_store.replace(stale, expected=stale)
        assert not b.target_file.exists()
        for malformed in ([], {}, {"version": 2}, {"version": 2, "persistent": True}):
            b.target_file.write_text(json.dumps(malformed), encoding="utf-8")
            assert b.target_store.read() is None
            assert b.request("get_edit_target", {})["error"] == "target_unbound"
    finally:
        b.close()


@pytest.mark.parametrize("crash", [False, True])
def test_actual_process_restart_restores_consent_after_exit_or_crash(work, tmp_path, crash):
    script = '''
import json, os, sys
from pathlib import Path
from uuid import uuid4
from wavelab.local_bridge import Bridge
from wavelab.mcp_server import rpc
from wavelab.workbench import Workbench
w = Workbench(Path(sys.argv[1]))
w.open_project(sys.argv[2])
b = Bridge(Path(sys.argv[3]))
sid = uuid4().hex
b.drain(sid, w)
if sys.argv[4] == "bind":
    b.bind_target(sid, w, persistent=True)
result = rpc("get_edit_target", runtime_dir=Path(sys.argv[3]))
result["binding_id"] = b.target_store.read()["binding_id"]
print(json.dumps(result), flush=True)
if sys.argv[5] == "crash":
    os._exit(0)
b.close()
'''
    directory = tmp_path / "runtime"
    common = [sys.executable, "-u", "-c", script, str(work.root), str(work.project_path), str(directory)]
    options = dict(capture_output=True, text=True, check=True, timeout=20)
    if sys.platform == "win32":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    first = json.loads(subprocess.run(common + ["bind", "crash" if crash else "exit"], **options).stdout)
    assert rpc("get_edit_target", runtime_dir=directory)["error"] == "target_offline"
    second = json.loads(subprocess.run(common + ["restore", "exit"], **options).stdout)
    assert "error" not in second and second["persistent"] and second["online"]
    assert first["binding_id"] == second["binding_id"]
    assert first["target"]["session_id"] != second["target"]["session_id"]
    assert first["target"]["project_epoch"] != second["target"]["project_epoch"]


def test_gui_explicit_persistence_and_restoration(work, tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import wavelab.local_bridge as module
    b = Bridge(tmp_path / "runtime")
    monkeypatch.setattr(module, "get_bridge", lambda directory: b)
    try:
        at = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30)
        at.session_state["workbench"] = work
        at.run()
        next(x for x in at.checkbox if x.label == "保持为 Codex 编辑目标").check().run()
        next(x for x in at.button if x.label == "设为 Codex 编辑目标").click().run()
        assert not at.exception
        assert b.request("get_edit_target", {})["persistent"]
        b.sessions[at.session_state["mcp_session_id"]].seen -= 20
        fresh = Workbench(work.root)
        fresh.open_project(work.project_path)
        again = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=30)
        again.session_state["workbench"] = fresh
        again.run()
        assert not again.exception
        assert b.request("get_edit_target", {})["target"]["session_id"] == again.session_state["mcp_session_id"]
        assert next(x for x in again.checkbox if x.label == "保持为 Codex 编辑目标").value
        next(x for x in again.button if x.label == "解除 Codex 编辑目标").click().run()
        assert not b.target_file.exists()
        assert not again.exception
    finally:
        b.close()

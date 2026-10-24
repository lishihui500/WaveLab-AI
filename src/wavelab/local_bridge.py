"""Loopback transport. Only the Streamlit script thread touches Workbench.

Queues contain requests, never a second editable FigureSpec. Expired browser
sessions reject requests; a timed-out queued request cannot execute later.
"""
import atexit
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from queue import Queue, Empty
import secrets
from threading import Event, Lock, Thread
from time import monotonic, perf_counter
from collections import deque
from uuid import uuid4

from pydantic import Field
from wavelab.commands.plot import StrictModel, Action, Plan, fingerprint, prepare, apply_proposal
from wavelab.ai.assistant import figure_context
from wavelab.mcp_protocol import identity
from wavelab.mcp_metrics import current as metrics_current, measure
from wavelab.coverage import coverage
from wavelab.target_binding import TargetStore, project_identity
from importlib.metadata import version

APPLICATION_VERSION = version("wavelab-ai")


class ApplyRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    expected_fingerprint: str
    expected_project_epoch: str
    actions: list[Action] = Field(min_length=1, max_length=100)
    user_request: str = Field(min_length=1, max_length=10000)


class SaveRequest(StrictModel):
    expected_revision: int = Field(ge=0)
    expected_fingerprint: str
    expected_project_epoch: str


def status(w, session_id):
    return dict(running=True, project_open=w.spec is not None, session_id=session_id,
                project_epoch=w.project_epoch, revision=w.revision,
                fingerprint=fingerprint(w.spec) if w.spec else None,
                panel_count=len(w.spec.panels) if w.spec else 0,
                channel_count=sum(len(m.channels) for m in w.spec.datasets) if w.spec else 0,
                modifications_allowed=w.spec is not None, protocol=identity(), application_version=APPLICATION_VERSION,
                project_name=w.project_path.parent.name if w.project_path else None, saved=w.save_status == "已保存")


def execute(w, session_id, method, params):
    """Must run on the owning GUI script thread, serial with manual callbacks."""
    current = status(w, session_id)
    if method == "get_wavelab_status":
        return current
    if w.spec is None:
        return dict(error="no_project", message="请先在目标工作台导入数据", **current)
    if method == "save_project":
        request = SaveRequest.model_validate(params)
        if (request.expected_revision, request.expected_fingerprint, request.expected_project_epoch) != (
                w.revision, fingerprint(w.spec), w.project_epoch):
            return dict(error="version_conflict", **current)
        if w.project_path is None:
            return dict(error="save_requires_gui", saved=False, message="请先在 GUI 命名并保存工程", **{k:v for k,v in current.items() if k != "saved"})
        path = w.project_path.resolve()
        expected = (w.root / "projects" / path.parent.name / "project.json").resolve()
        if path != expected or path.parent.parent != (w.root / "projects").resolve() or not path.is_file():
            return dict(error="save_requires_gui", message="当前工程路径需先由 GUI 确认", **current)
        try:
            with measure("project_save_ms"):
                w.save_project(path.parent.name)
                document = json.loads(path.read_text(encoding="utf-8"))
                actual = document["figure"]
                wanted = w.spec.model_dump(mode="json")
                for stored, source in zip(actual["datasets"], wanted["datasets"], strict=True):
                    stored["source_path"] = source["source_path"]
                if actual != wanted:
                    raise ValueError("保存后回读不一致")
        except (OSError, ValueError, TypeError, KeyError):
            w.save_error = "MCP 保存或保存后回读校验失败"
            return dict(error="save_failed", saved_revision=None, **{**status(w, session_id), "saved": False})
        return dict(saved_revision=w.revision, saved_fingerprint=fingerprint(w.spec), **status(w, session_id))
    if method == "get_figure_context":
        with measure("state_read_ms"):
            context = figure_context(w)
            summary = coverage(w, params.get("window_s"))
        return dict(context=context, coverage=summary, **current)
    if method == "get_channel_metadata":
        context = figure_context(w)
        for dataset in context["datasets"]:
            for channel in dataset["channels"]:
                if channel["channel_id"] == params.get("channel_id"):
                    placements = [dict(panel_id=p.id, **s.model_dump(mode="json", exclude={"confirmation_source"}))
                                  for p in w.spec.panels for s in p.series if s.channel_id == channel["channel_id"]]
                    return dict(channel=channel, dataset_id=dataset["dataset_id"], placements=placements, **current)
        return dict(error="unknown_channel", **current)
    if method != "apply_plot_actions":
        return dict(error="unknown_method")
    request = ApplyRequest.model_validate(params)
    if (request.expected_revision, request.expected_fingerprint, request.expected_project_epoch) != (
            w.revision, fingerprint(w.spec), w.project_epoch):
        return dict(error="version_conflict", message="状态已变化，请重新读取后按原始意图生成操作", **current)
    plan = Plan(summary="Codex 本地绘图操作", actions=request.actions)
    with measure("action_prepare_validate_ms"):
        proposal = prepare(w, plan, request.user_request)
    with measure("action_commit_ms"):
        result = apply_proposal(w, proposal)
    # Do not expose nested source confirmation text through panel-add/remove diffs.
    result["change_count"] = len(result.pop("changes"))
    return dict(result=result, **status(w, session_id))


@dataclass
class Pending:
    method: str
    params: dict
    done: Event = field(default_factory=Event)
    lock: Lock = field(default_factory=Lock)
    cancelled: bool = False
    result: dict | None = None
    queued_at: float = field(default_factory=monotonic)
    request_id: str = field(default_factory=lambda: uuid4().hex)
    binding_id: str | None = None


class Session:
    def __init__(self):
        self.queue = Queue(maxsize=32)
        self.seen = monotonic()
        self.project_epoch = None
        self.project_identity = None
        self.binding_id = None


class Bridge:
    def __init__(self, directory):
        self.sessions = {}
        self.performance_records = deque(maxlen=256)
        self.lock = Lock()
        self.token = secrets.token_urlsafe(32)
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass  # Neither tokens nor source metadata enter HTTP logs.

            def do_POST(self):
                try:
                    if self.headers.get("Origin") or self.headers.get("Authorization") != "Bearer " + bridge.token:
                        self.send_error(403)
                        return
                    size = int(self.headers.get("Content-Length", "0"))
                    if self.path != "/rpc" or not 0 < size <= 262144:
                        self.send_error(400)
                        return
                    request = json.loads(self.rfile.read(size))
                    if request.get("protocol") != identity():
                        result = dict(error="protocol_mismatch", message="绘图协议不一致，请重启/重新连接 MCP 和 WaveLab", protocol=identity())
                    else:
                        result = bridge.request(request["method"], request.get("params", {}), request.get("session_id"), request_id=request.get("request_id"))
                except Exception:
                    result = dict(error="invalid_request", message="无效的本地请求")
                result.setdefault("protocol", identity())
                request_data = locals().get("request")
                request_data = request_data if isinstance(request_data, dict) else {}
                rid = request_data.get("request_id")
                if not isinstance(rid, str) or len(rid) != 32 or any(c not in "0123456789abcdef" for c in rid):
                    rid = uuid4().hex
                result.setdefault("diagnostics", dict(request_id=rid, stages_ms={}, success="error" not in result))
                encoded_at = perf_counter()
                body = json.dumps(result, ensure_ascii=False).encode()
                diagnostic = result.get("diagnostics")
                if diagnostic:
                    diagnostic["stages_ms"]["rpc_response_encode_ms"] = (perf_counter() - encoded_at) * 1000
                    bridge.performance_records.append(dict(request_id=diagnostic["request_id"],
                        method=request_data.get("method") if isinstance(request_data.get("method"), str) and request_data.get("method") in {"list_sessions", "get_edit_target", "get_wavelab_status", "get_figure_context", "get_channel_metadata", "apply_plot_actions", "save_project"} else "unknown",
                        success=diagnostic["success"], stages_ms=diagnostic["stages_ms"].copy()))
                    body = json.dumps(result, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            import subprocess
            import getpass
            account = os.environ.get("USERDOMAIN", ".") + "\\" + getpass.getuser()
            subprocess.run(["icacls", str(directory), "/inheritance:r", "/grant:r", account + ":(OI)(CI)F"],
                           check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            directory.chmod(0o700)
        self.target_file = directory / "codex-target.json"
        self.target_store = TargetStore(self.target_file)
        self.descriptor = directory / (uuid4().hex + ".json")
        self.descriptor.write_text(json.dumps(dict(port=self.server.server_port, token=self.token)), encoding="utf-8")
        self.descriptor.chmod(0o600)
        Thread(target=self.server.serve_forever, daemon=True).start()
        atexit.register(self.close)

    def close(self):
        record = self.target_store.read()
        if record and record["endpoint_id"] == self.descriptor.stem and not record["persistent"]:
            self.target_store.replace(None, expected=record)
        self.server.shutdown()
        self.server.server_close()
        self.descriptor.unlink(missing_ok=True)

    def attach(self, session_id, w=None):
        with self.lock:
            session = self.sessions.setdefault(session_id, Session())
            session.seen = monotonic()
            if w is not None:
                session.project_epoch = w.project_epoch
                session.project_identity = project_identity(w)
        if w is not None:
            self._sync_target(session_id, session)
        return session

    def _owner_running(self, record):
        """Probe only the explicitly selected endpoint, never discover by name."""
        from urllib.request import Request, ProxyHandler, build_opener
        endpoint_id = record["endpoint_id"]
        if len(endpoint_id) != 32 or any(c not in "0123456789abcdef" for c in endpoint_id):
            return True  # Invalid identity is not permission to take ownership.
        try:
            endpoint = json.loads(self.descriptor.with_name(endpoint_id + ".json").read_text(encoding="utf-8"))
            port = endpoint["port"]
            if type(port) is not int or not 0 < port < 65536:
                return True
            request = Request(f"http://127.0.0.1:{port}/rpc",
                json.dumps(dict(method="list_sessions", protocol=identity())).encode(),
                {"Authorization": "Bearer " + endpoint["token"]})
            with build_opener(ProxyHandler({})).open(request, timeout=1):
                return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _sync_target(self, session_id, session):
        record = self.target_store.read()
        if record is None:
            return
        owned = record["endpoint_id"] == self.descriptor.stem
        selected = owned and record["target"]["session_id"] == session_id
        if selected:
            valid = (session.project_identity == record["project_identity"] if record["persistent"]
                     else session.project_epoch == record["target"]["project_epoch"])
            if not valid:
                self.target_store.replace(None, expected=record)
                return
            if session.project_epoch == record["target"]["project_epoch"]:
                session.binding_id = record["binding_id"]
                return
        elif not record["persistent"] or session.project_identity != record["project_identity"]:
            return
        elif owned:
            with self.lock:
                previous = self.sessions.get(record["target"]["session_id"])
                if previous and monotonic() - previous.seen < 15:
                    return  # An existing live selection always wins.
                matches = [s for s in self.sessions.values() if monotonic() - s.seen < 15
                           and s.project_identity == record["project_identity"]]
                if len(matches) != 1:
                    return
        elif self._owner_running(record):
            return  # Another running workbench retains its explicit selection.
        restored = dict(record, endpoint_id=self.descriptor.stem,
                        target=dict(session_id=session_id, project_epoch=session.project_epoch))
        if self.target_store.replace(restored, expected=record):
            session.binding_id = restored["binding_id"]

    def bind_target(self, session_id, w, *, persistent=False):
        # GUI callback only. Persist an identity, never editable project contents.
        if w.spec is None:
            raise ValueError("请先打开工程")
        stable = project_identity(w)
        if persistent and (stable is None or w.saved_spec is None
                or sorted((m.dataset_id, m.source_sha256) for m in w.spec.datasets)
                   != sorted((m.dataset_id, m.source_sha256) for m in w.saved_spec.datasets)):
            raise ValueError("请先在 GUI 保存当前工程，再启用持久编辑目标")
        self.attach(session_id, w)
        record = dict(version=2, binding_id=uuid4().hex, persistent=persistent,
            project_identity=stable if persistent else None, endpoint_id=self.descriptor.stem,
            target=dict(session_id=session_id, project_epoch=w.project_epoch))
        self.target_store.replace(record)
        self.sessions[session_id].binding_id = record["binding_id"]

    def unbind_target(self, session_id):
        record = self.target_store.read()
        if record and record["endpoint_id"] == self.descriptor.stem and record["target"]["session_id"] == session_id:
            self.target_store.replace(None, expected=record)

    def request(self, method, params, session_id=None, timeout=30, request_id=None):
        with self.lock:
            active = {sid: s for sid, s in self.sessions.items() if monotonic() - s.seen < 15}
        if method == "get_edit_target":
            record = self.target_store.read()
            if not record or record["endpoint_id"] != self.descriptor.stem:
                return dict(error="target_unbound")
            result = dict(target=record["target"], persistent=record["persistent"],
                          online=record["target"]["session_id"] in active, protocol=identity())
            if not result["online"]:
                result.update(error="target_offline", message="编辑目标离线；请恢复目标页面连接，目标选择已保留")
            return result
        if method == "list_sessions":
            return dict(sessions=list(active))
        if session_id not in active:
            record = self.target_store.read()
            if record and record["endpoint_id"] == self.descriptor.stem and record["target"]["session_id"] == session_id:
                return dict(error="target_offline", message="编辑目标离线，请恢复页面连接后重新读取状态")
            return dict(error="session_required" if active else "not_running", sessions=list(active))
        queued = monotonic()
        pending = Pending(method, params)
        record = self.target_store.read()
        selected = record and record["endpoint_id"] == self.descriptor.stem and record["target"]["session_id"] == session_id
        if method in {"apply_plot_actions", "save_project"} and not selected and (record or active[session_id].binding_id):
            return dict(error="target_changed", message="编辑目标已变化，请重新读取目标和工程状态")
        if selected:
            pending.binding_id = record["binding_id"]
        if isinstance(request_id, str) and len(request_id) == 32 and all(c in "0123456789abcdef" for c in request_id):
            pending.request_id = request_id
        try:
            active[session_id].queue.put_nowait(pending)
        except Exception:
            return dict(error="busy")
        pending.enqueue_ms = (monotonic() - queued) * 1000
        if not pending.done.wait(timeout):
            # drain holds this lock while executing: an already-started command
            # returns its real result, while an unstarted command is cancelled.
            with pending.lock:
                if not pending.done.is_set():
                    pending.cancelled = True
                    return dict(error="gui_unresponsive", message="请求未执行，请保持目标工作台页面连接")
        return pending.result

    def drain(self, session_id, w):
        session = self.attach(session_id, w)
        before = w.revision
        for _ in range(8):
            try:
                pending = session.queue.get_nowait()
            except Empty:
                break
            with pending.lock:
                if not pending.cancelled:
                    try:
                        record = self.target_store.read()
                        if pending.binding_id and (not record or record["binding_id"] != pending.binding_id
                                or record["endpoint_id"] != self.descriptor.stem
                                or record["target"] != dict(session_id=session_id, project_epoch=w.project_epoch)):
                            pending.result = dict(error="target_changed", message="编辑目标已变化，请重新读取目标和工程状态")
                            pending.result["diagnostics"] = dict(request_id=pending.request_id, stages_ms={}, success=False)
                            pending.done.set()
                            continue
                        timings = dict(request_enqueue_ms=getattr(pending, "enqueue_ms", 0), gui_queue_wait_ms=(monotonic() - pending.queued_at) * 1000)
                        token = metrics_current.set(timings)
                        try:
                            with measure("gui_execute_ms"):
                                pending.result = execute(w, session_id, pending.method, pending.params)
                        finally:
                            metrics_current.reset(token)
                        pending.result["diagnostics"] = dict(request_id=pending.request_id, stages_ms=timings,
                                                            success="error" not in pending.result)
                    except (ValueError, KeyError, IndexError, TypeError) as exc:
                        pending.result = dict(error="validation_error", message=str(exc), **status(w, session_id))
                    except Exception:
                        pending.result = dict(error="execution_failed", message="执行失败，请检查工作台", **status(w, session_id))
                if pending.result is not None and "diagnostics" not in pending.result:
                    pending.result["diagnostics"] = dict(request_id=pending.request_id, stages_ms=locals().get("timings", {}), success=False)
                pending.done.set()
        return w.revision != before


if "_bridges" not in globals():
    _bridges = {}
    _bridges_lock = Lock()


def get_bridge(directory):
    key = str(Path(directory).resolve())
    with _bridges_lock:
        if key not in _bridges:
            _bridges[key] = Bridge(key)
        return _bridges[key]

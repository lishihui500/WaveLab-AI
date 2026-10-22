"""Stdio adapter with bounded transport cache; never instantiates Workbench."""
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen, ProxyHandler, build_opener


# Bounded route cache contains transport identities only; GUI validates every request.
from time import monotonic, perf_counter
from threading import Lock
from uuid import uuid4
from wavelab.mcp_protocol import identity

_routes = {}
_route_lock = Lock()
ROUTE_TTL_S = 30


def rpc(method, params=None, session_id=None, runtime_dir=None):
    begin = perf_counter()
    directory = Path(runtime_dir or os.environ.get("WAVELAB_RUNTIME_DIR", Path(__file__).resolve().parents[2] / ".wavelab" / "runtime"))
    opener = build_opener(ProxyHandler({}))
    stages = {}
    request_id = uuid4().hex

    def call(route, operation, sid=None):
        transport_start = perf_counter()
        url, headers = route
        request = Request(url, json.dumps(dict(method=operation, params=params or {}, session_id=sid,
                                              protocol=identity(), request_id=request_id)).encode(), headers)
        with opener.open(request, timeout=120 if operation not in {"list_sessions", "get_edit_target"} else 1) as response:
            result = json.load(response)
        stages["rpc_transport_ms"] = stages.get("rpc_transport_ms", 0) + (perf_counter() - transport_start) * 1000
        if result.get("protocol") != identity():
            return dict(error="protocol_mismatch", message="GUI/MCP 绘图协议不一致，请重启或重新连接双方", protocol=identity())
        if operation == "list_sessions":
            result.pop("protocol", None)
        return result

    def finish(result):
        diagnostic = result.setdefault("diagnostics", {})
        diagnostic.setdefault("request_id", request_id)
        diagnostic.setdefault("stages_ms", {}).update(stages)
        diagnostic["stages_ms"]["rpc_total_ms"] = (perf_counter() - begin) * 1000
        diagnostic["success"] = "error" not in result
        # Preserve legacy list response shape.
        if method == "list_sessions":
            result.pop("diagnostics", None)
        return result

    route_started = perf_counter()
    key = (str(directory.resolve()), session_id)
    route = None
    with _route_lock:
        cached = _routes.get(key)
    if session_id and cached and monotonic() - cached[0] < ROUTE_TTL_S:
        stages["session_route_ms"] = (perf_counter() - route_started) * 1000
        try:
            result = call(cached[1], method, session_id)
            if result.get("error") not in {"session_required", "not_running"}:
                return finish(result)
        except (OSError, ValueError):
            with _route_lock:
                _routes.pop(key, None)
            if method in {"apply_plot_actions", "save_project"}:
                return finish(dict(error="connection_lost", message="执行结果未知；重新读取状态，勿重试写入"))
    found, targets = [], []
    discovery = perf_counter()
    descriptors = list(directory.glob("*.json"))
    if method == "get_edit_target":
        # One atomic GUI selection determines its exact endpoint. No all-session scan.
        try:
            binding = json.loads((directory / "codex-target.json").read_text(encoding="utf-8"))
            endpoint_id = binding["endpoint_id"]
            if len(endpoint_id) != 32 or any(c not in "0123456789abcdef" for c in endpoint_id):
                raise ValueError("invalid endpoint identity")
            descriptors = [directory / (endpoint_id + ".json")]
        except (OSError, ValueError, KeyError, TypeError):
            return finish(dict(error="target_unbound"))
    incompatible = False
    for descriptor in descriptors:
        try:
            endpoint = json.loads(descriptor.read_text(encoding="utf-8"))
            port = endpoint["port"]
            if type(port) is not int or not 0 < port < 65536:
                continue
            candidate = (f"http://127.0.0.1:{port}/rpc", {"Authorization": "Bearer " + endpoint["token"], "Content-Type": "application/json"})
            listing = call(candidate, "get_edit_target" if method == "get_edit_target" else "list_sessions")
            if listing.get("error") == "protocol_mismatch":
                if method == "get_edit_target":
                    return finish(listing)
                incompatible = True
                continue
            if method == "get_edit_target":
                if "target" in listing:
                    targets.append((listing, candidate))
            else:
                found.extend((sid, candidate) for sid in listing.get("sessions", []))
        except (OSError, ValueError, KeyError):
            continue
    stages["endpoint_discovery_ms"] = (perf_counter() - discovery) * 1000
    routing = perf_counter()
    if method == "get_edit_target":
        if len(targets) != 1:
            return finish(dict(error="target_unbound" if not targets else "target_ambiguous"))
        result, route = targets[0]
        sid = result["target"]["session_id"]
        with _route_lock:
            _routes[(str(directory.resolve()), sid)] = (monotonic(), route)
        return finish(result)
    if method == "list_sessions":
        return finish(dict(sessions=[sid for sid, _ in found]) if found else dict(error="not_running", sessions=[]))
    matches = [r for sid, r in found if sid == session_id]
    if len(matches) != 1:
        if not matches and incompatible:
            return finish(dict(error="protocol_mismatch", message="发现旧 GUI 协议；请重启目标 WaveLab 进程"))
        return finish(dict(error="session_required" if found else "not_running", sessions=[sid for sid, _ in found]))
    route = matches[0]
    with _route_lock:
        _routes[key] = (monotonic(), route)
        if len(_routes) > 256:
            _routes.clear()
    stages["session_route_ms"] = (perf_counter() - routing) * 1000
    try:
        return finish(call(route, method, session_id))
    except (OSError, ValueError):
        with _route_lock:
            _routes.pop(key, None)
        return finish(dict(error="connection_lost", message="连接中断；执行结果未知，重新读取状态，勿盲目重试写入"))


def create_server(runtime_dir=None):
    # Initialize NumPy-backed schema modules before stdio/AnyIO starts workers.
    # On this Windows/Python host a first C-extension import inside a tool call
    # can block its native module initialization. No Workbench is instantiated.
    from wavelab.mcp_protocol import action_schema as schema_document
    action_schema = dict(schema_document(), protocol=identity())
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("WaveLab", instructions="Read status/context first. Use exact session, project epoch, revision and fingerprint. Never infer physical mappings or event times. Conflicts require rereading. Only user-requested plotting changes; no model API calls.")

    @server.tool()
    def get_wavelab_status(session_id: str | None = None) -> dict:
        """Without session_id list connected GUI sessions; select explicitly before use."""
        return rpc("get_wavelab_status" if session_id else "list_sessions", session_id=session_id, runtime_dir=runtime_dir)

    @server.tool()
    def get_figure_context(session_id: str, window_s: list[float] | None = None) -> dict:
        """Actual current ordered FigureSpec and sanitized metadata, no samples or paths."""
        return rpc("get_figure_context", dict(window_s=window_s), session_id=session_id, runtime_dir=runtime_dir)

    @server.tool()
    def get_channel_metadata(session_id: str, channel_id: str) -> dict:
        """Confirmed channel semantics and all current series placements/styles."""
        return rpc("get_channel_metadata", dict(channel_id=channel_id), session_id, runtime_dir)

    @server.tool()
    def apply_plot_actions(session_id: str, expected_project_epoch: str, expected_revision: int,
                           expected_fingerprint: str, actions: list[dict], user_request: str) -> dict:
        """Execute existing whitelisted Action batch atomically as one undo unit.

        Read get_plot_action_schema first. user_request is the user's actual text;
        event times require evidence_quote from that text or a confirmed event.
        """
        return rpc("apply_plot_actions", dict(expected_project_epoch=expected_project_epoch,
                   expected_revision=expected_revision, expected_fingerprint=expected_fingerprint,
                   actions=actions, user_request=user_request), session_id, runtime_dir)

    @server.tool()
    def get_edit_target() -> dict:
        """Read the unique GUI-selected Codex target. Never guess; cache returned session identity."""
        return rpc("get_edit_target", runtime_dir=runtime_dir)

    @server.tool()
    def save_project(session_id: str, expected_project_epoch: str, expected_revision: int,
                     expected_fingerprint: str) -> dict:
        """Only on an explicit user save request. Save the existing current project on its GUI thread.

        No path/name arguments; unnamed/external projects require initial GUI save.
        Check saved and saved_revision, never infer success from submission.
        """
        return rpc("save_project", dict(expected_project_epoch=expected_project_epoch,
                   expected_revision=expected_revision, expected_fingerprint=expected_fingerprint), session_id, runtime_dir)

    @server.tool()
    def get_quantity_presets() -> dict:
        """Read electrical quantity IDs, bilingual names, unit candidates and SI conversion families.

        Channel.unit is the source unit; set_axis_quantity/set_display_unit only
        change panel display. set_channel_properties edits source channel defaults;
        source quantities/units require verbatim user evidence. Old axis override actions are retired.
        pu/% conversions need a defined base.
        """
        from dataclasses import asdict
        from wavelab.quantity_presets import QuantityLibrary, UNITS
        directory = Path(runtime_dir or os.environ.get("WAVELAB_RUNTIME_DIR", Path(__file__).resolve().parents[2] / ".wavelab" / "runtime"))
        library = QuantityLibrary(directory.parent)
        return dict(quantities=[asdict(q) for q in library.presets().values()], recent=library.recent(),
                    units={k:asdict(v) for k,v in UNITS.items()}, source_unit_field="Channel.unit",display_unit_field="automatic_from_channels")

    @server.tool()
    def get_plot_action_schema() -> dict:
        """Exact supported Action schema, fields, targets and inset time/geometry rules."""
        return action_schema

    return server


def main():
    create_server().run(transport="stdio")


if __name__ == "__main__":
    main()

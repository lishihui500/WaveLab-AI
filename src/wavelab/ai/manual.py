"""Local request/response exchange. No network, credentials or generated code."""
from dataclasses import dataclass
from wavelab.domain.figure import FigureSpec
import json
import re
from time import perf_counter
from typing import Annotated
from uuid import uuid4

from pydantic import Field, TypeAdapter, ValidationError

from wavelab.commands import Plan, prepare, apply_proposal, tool_definitions
from wavelab.commands.plot import StrictModel, ALLOWED, MODELS, TARGETS, fingerprint
from .assistant import figure_context
from .provider import MANUAL_SYSTEM


class ManualResponse(StrictModel):
    request_id: str
    revision: int = Field(ge=0)
    fingerprint: str
    plan: Plan


def protocol():
    """Generate patch types AND constraints from the executor's actual models."""
    return {**tool_definitions(), "output_schema": ManualResponse.model_json_schema(),
            "targets_by_action": {key: sorted(value) for key, value in TARGETS.items()},
            "patch_schema_by_action": {
                kind: {name: TypeAdapter(Annotated[MODELS[kind].model_fields[name].annotation,
                                                  MODELS[kind].model_fields[name]]).json_schema()
                       for name in sorted(names)} for kind, names in ALLOWED.items()}}


def compact_protocol(selected=None):
    """One response schema, patch constraints derived from executor models."""
    result = protocol()
    result.pop("response_schema")
    if selected is not None:
        selected = set(selected)
        result["allowed_changes"] = {k: v for k, v in result["allowed_changes"].items() if k in selected}
        result["targets_by_action"] = {k: v for k, v in result["targets_by_action"].items() if k in selected}
        result["patch_schema_by_action"] = {k: v for k, v in result["patch_schema_by_action"].items() if k in selected}
        result["output_schema"]["$defs"]["Action"]["properties"]["action"]["enum"] = sorted(selected)
    return result


def task_context(w, request, scope="auto", panel_id=None):
    if scope not in {"auto", "figure", "all"}:
        raise ValueError("未知上下文范围")
    context = figure_context(w)
    # Only an unambiguous whole instruction selects the narrow protocol.
    # All other natural language retains the complete command set and metadata.
    simple = bool(re.fullmatch(r"(?:请)?(?:将|让)?(?:当前|全部|所有|当前子图)?(?:六条|6条|已绘制的)?曲线的?图例(?:名字|名称)?[，, ]*(?:与|和|等于|使用|同步为|同步到)(?:其对应)?通道(?:的)?(?:显示)?名称(?:改成一致的|保持一致|一致)?[。！! ]*", request.strip()))
    selected = {"query_context"} if scope == "auto" and simple else None
    if selected and "当前" in request and not any(word in request for word in ("当前子图", "当前六条", "当前6条")):
        selected = None
    if selected and "当前" in request:
        if panel_id not in {p["id"] for p in context["panels"]}:
            selected = None
        else:
            context["panels"] = [p for p in context["panels"] if p["id"] == panel_id]
            context["active_panel_id"] = panel_id
    if selected or scope == "figure":
        used = {series["channel_id"] for panel in context["panels"] for series in panel["series"]}
        context["datasets"] = [{"dataset_id": m["dataset_id"], "channels": [c for c in m["channels"] if c["channel_id"] in used]} for m in context["datasets"] if any(c["channel_id"] in used for c in m["channels"])]
        context["context_scope"] = "已绘制曲线；范围外目标不在快照中时直接自然语言说明缺少上下文，再选择全部数据集重新生成"
    else:
        context["context_scope"] = "全部脱敏元数据，含未绘制通道"
    if selected:
        context = {"panels": [{"id": p["id"], "series": [{"channel_id": x["channel_id"], "legend_source": "channel"} for x in p["series"]]} for p in context["panels"]], "datasets": context["datasets"], "context_scope": context["context_scope"]}
    return context, selected


def parse_response(raw):
    if len(raw) > 250_000:
        raise ValueError("JSON 超过 250000 字符，请缩短方案")
    text = raw.strip().lstrip("\ufeff").strip()
    if text.startswith("```"):
        match = re.fullmatch(r"```(?:json)?\s*\n([\s\S]*?)\n```", text, flags=re.I)
        if not match:
            raise ValueError("只接受纯 JSON 或单层完整的 JSON 代码块，不接受前后说明")
        text = match.group(1)
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"JSON 字段重复：{key}")
            obj[key] = value
        return obj
    try:
        # Reject duplicate fields before Pydantic's JSON validator can discard them.
        json.loads(text, object_pairs_hook=unique)
        return ManualResponse.model_validate_json(text)
    except ValidationError as exc:
        details = [f"{'.'.join(map(str, e['loc'])) or 'JSON'}：{e['msg']}"
                   for e in exc.errors(include_input=False, include_url=False)[:8]]
        raise ValueError("方案字段校验失败：\n" + "\n".join(details)) from None
    except (json.JSONDecodeError, RecursionError):
        raise ValueError("无法解析最终 JSON：澄清问题请直接在 ChatGPT 中回答，无需重新导出快照；此处仅粘贴完整最终方案") from None


@dataclass(frozen=True)
class RequestSnapshot:
    request_id: str
    revision: int
    fingerprint: str
    request: str
    prompt: str
    base: FigureSpec
    project_epoch: str
    history_epoch: int


class ManualExchange:
    def __init__(self):
        self.snapshot = None
        self._workbench = None
        self.proposal = None
        self.response = None
        self.status = "idle"
        self.records = []
        self._closed = False
        self.validated_raw = None
        self.confirmation = ""
        self.manual_changes = []
        self.ai_changes = []
        self.merge_state = "unchanged"

    def bound(self, w):
        return bool(self.snapshot and self._workbench is w and w.spec is not None
                    and self.snapshot.project_epoch == w.project_epoch)

    def current(self, w):
        s = self.snapshot
        return bool(s and self._workbench is w and w.spec is not None
                    and s.revision == w.revision and s.fingerprint == fingerprint(w.spec))

    def generate(self, w, request, *, scope="auto", panel_id=None):
        if not request.strip() or len(request) > 8000:
            raise ValueError("绘图要求需为 1–8000 字符")
        context, selected = task_context(w, request, scope, panel_id)
        request_id, base = str(uuid4()), fingerprint(w.spec)
        binding = dict(request_id=request_id, revision=w.revision, fingerprint=base)
        document = {"binding": binding, "user_request": request, "figure_context": context,
                    "protocol": compact_protocol(selected),
                    "output_example": {**binding, "plan": {"summary": "格式示例：仅查询上下文；实际动作按用户任务生成",
                                                          "clarification": None, "actions": [{"action": "query_context", "changes": {}}]}}}
        prompt = MANUAL_SYSTEM + "\n\n" + ("{\n" + ",\n".join(json.dumps(k) + ": " + json.dumps(v, ensure_ascii=False, indent=None if k == "protocol" else 2) for k, v in document.items()) + "\n}")
        self.snapshot = RequestSnapshot(request_id, w.revision, base, request, prompt, w.spec, w.project_epoch, w.history_epoch)
        self._workbench = w
        self._closed = False
        self.confirmation = ""
        self.proposal, self.response, self.status = None, None, "exported"
        self.validated_raw = None
        return self.snapshot

    def validate(self, w, raw, *, source="manual_unverified", confirmation=""):
        # Source is a user-declared provenance, never evidence of a real model call.
        if source not in {"manual_unverified", "scripted_json", "mock", "user_chatgpt"}:
            raise ValueError("未知方案来源")
        self.proposal, self.response = None, None
        self.validated_raw = None
        start = perf_counter()
        try:
            if not self.bound(w) or self._closed:
                raise ValueError("请求已过期或不属于当前工程，请重新生成请求")
            if len(confirmation) > 8000:
                raise ValueError("后续确认原话不能超过 8000 字符")
            self.confirmation = confirmation
            response = parse_response(raw)
            s = self.snapshot
            if (response.request_id, response.revision, response.fingerprint) != (s.request_id, s.revision, s.fingerprint):
                raise ValueError("返回方案与本地请求快照不匹配，请复制最新请求重新生成方案")
            self.response = response
            if response.plan.clarification:
                self.status = "clarification"
            else:
                self.proposal = self.reconcile(w, response.plan)
                self.status = "proposed"
                self.validated_raw = raw
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            self.status = "failed"
            self._record(w, source, perf_counter() - start, str(exc))
            raise ValueError(str(exc)) from None
        self._record(w, source, perf_counter() - start)
        return self.proposal

    def reconcile(self, w, plan):
        s = self.snapshot
        if not self.bound(w):
            raise ValueError("请求不属于当前工程，请重新生成请求")
        if not self.current(w):
            raise ValueError("绘图状态已改变，旧快照已过期；请重新生成快照和最终方案")
        if s.history_epoch != w.history_epoch:
            raise ValueError("撤销/恢复改变了历史依赖，请重新生成请求")
        request = s.request + ("\n用户后续确认：\n" + self.confirmation if self.confirmation else "")
        proposal = prepare(w, plan, request)
        self.manual_changes = []
        self.ai_changes = proposal.changes
        self.merge_state = "unchanged"
        return proposal

    def apply(self, w):
        if not self.bound(w) or self._closed or self.status != "proposed" or self.proposal is None:
            raise ValueError("没有当前工程的有效待应用方案；旧方案请重新生成")
        if not self.current(w) or self.snapshot.history_epoch != w.history_epoch:
            self.proposal = None
            self.status = "failed"
            raise ValueError("绘图状态已改变，旧快照已过期；请重新生成快照和最终方案")
        result = apply_proposal(w, self.proposal)
        self.status = "applied"
        self._closed = True
        self.records[-1]["execution_success"] = True
        self.records[-1]["current_revision"] = w.revision
        return result

    def cancel(self):
        self.proposal = None
        self.status = "cancelled"
        self._closed = True

    def _record(self, w, source, elapsed_s, error=None):
        self.records.append({"source": source, "model_generation_verified": False,
                             "request_id": self.snapshot.request_id if self.snapshot else None,
                             "base_revision": self.snapshot.revision if self.snapshot else None,
                             "current_revision": w.revision, "status": self.status,
                             "validation_success": self.proposal is not None,
                             "execution_success": False, "final_intent_correct": None,
                             "local_elapsed_s": elapsed_s, "model_calls": 0,
                             "model_elapsed_s": None, "tokens": None,
                             "error": error})
        self.records = self.records[-200:]

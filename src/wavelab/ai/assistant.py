"""Consent, bounded repair, revision guards and privacy-minimal evaluation records."""
from dataclasses import dataclass
import json
from time import perf_counter

from wavelab.commands import prepare, apply_proposal, tool_definitions
from wavelab.commands.plot import fingerprint
from .provider import ProviderError


def figure_context(w):
    if not w.spec:
        raise ValueError("请先导入数据")
    payload = w.spec.model_dump(mode="json")
    payload.pop("datasets")
    for panel in payload["panels"]:
        for series in panel["series"]:
            series.pop("confirmation_source", None)
    for event in payload["events"]:
        event.pop("confirmation_source", None)
        event["confirmed"] = True
    payload["datasets"] = [{"dataset_id": m.dataset_id,
                            "channels": [{"channel_id": c.channel_id, "source_column_index": c.source_column_index,
                                          "group_name": c.group_name, "group_index": c.group_index, "display_name": c.display_name,
                                          "unit": c.unit, "unit_confirmed": bool(c.unit), "quantity": ({"preset_id": c.quantity.preset_id, "zh": c.quantity.zh, "en": c.quantity.en, "unit": c.quantity.unit, "confirmed": True} if c.quantity else None), "physical_role": c.physical_role, "mapping_confirmed": bool(c.physical_role and c.confirmation_source)} for c in m.channels],
                            "groups": [{"group_name": g.group_name, "channel_ids": list(g.channel_ids)} for g in m.groups]} for m in w.spec.datasets]
    payload["revision"] = w.revision
    from dataclasses import asdict
    from wavelab.quantity_presets import QuantityLibrary
    payload["custom_quantity_presets"] = [dict(asdict(q),units=list(q.units)) for q in QuantityLibrary(w.root).presets().values() if q.id.startswith("custom_")]
    return payload


@dataclass
class Turn:
    request: str
    result: object | None = None
    proposal: object | None = None
    status: str = "pending"
    error: str | None = None
    calls: int = 0
    elapsed_s: float = 0
    usage: dict | None = None
    base_revision: int = 0
    mode: str = "unknown"


class Assistant:
    def __init__(self):
        self.turns = []
        self.records = []

    def propose(self, w, provider, request, *, consent=False, max_repairs=1):
        if not consent:
            raise ValueError("首次发送工程元数据前，需要明确确认外传范围及 API 费用")
        if not request.strip() or len(request) > 8000 or not 0 <= max_repairs <= 2:
            raise ValueError("请求需为 1–8000 字符，自动纠错次数为 0–2")
        context = figure_context(w)
        revision, base = w.revision, fingerprint(w.spec)
        turn = Turn(request, base_revision=revision)
        history = [{"request": t.request, "status": t.status, "summary": t.result.plan.summary if t.result else ""} for t in self.turns[-6:]]
        # Replaced pending plans can never be applied by accident.
        for old in self.turns:
            if old.status == "proposed":
                old.status = "superseded"
                old.proposal = None
        self.turns.append(turn)
        self.turns = self.turns[-30:]
        start, feedback = perf_counter(), None
        turn.usage = {}
        try:
            for attempt in range(max_repairs + 1):
                turn.calls += 1
                try:
                    result = provider.generate_actions(request, context, tool_definitions(), history, feedback)
                except ProviderError as exc:
                    if exc.code == "invalid_output" and attempt < max_repairs:
                        feedback = {"code": exc.code, "message": "Return a valid Plan JSON, no extra fields."}
                        continue
                    raise
                turn.result, turn.mode = result, result.mode
                for key, value in result.usage.items():
                    turn.usage[key] = turn.usage.get(key, 0) + value
                if revision != w.revision or base != fingerprint(w.spec):
                    raise ValueError("模型调用期间图形已修改；请重新生成方案")
                if result.plan.clarification:
                    turn.status = "clarification"
                    break
                try:
                    turn.proposal = prepare(w, result.plan, request)
                    turn.status = "proposed"
                    break
                except (ValueError, TypeError, KeyError, IndexError) as exc:
                    if attempt == max_repairs:
                        raise ValueError(str(exc)) from None
                    feedback = {"code": "command_validation", "message": str(exc)[:2000]}
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            turn.status, turn.error = "failed", str(exc)
        turn.elapsed_s = perf_counter() - start
        self.record(turn, w)
        return turn

    def apply(self, w, turn):
        if turn.status != "proposed" or turn.proposal is None:
            raise ValueError("没有待应用的有效方案")
        try:
            result = apply_proposal(w, turn.proposal)
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            turn.status, turn.error = "failed", str(exc)
            self.record(turn, w)
            raise
        turn.status = "applied"
        self.record(turn, w)
        return result

    def cancel(self, turn, w):
        turn.status, turn.proposal = "cancelled", None
        self.record(turn, w)

    def record(self, turn, w):
        self.records.append({"mode": turn.mode, "model": turn.result.model if turn.result else None,
                             "status": turn.status, "action_types": [a.action for a in turn.result.plan.actions] if turn.result else [],
                             "base_revision": turn.base_revision, "current_revision": w.revision,
                             "calls": turn.calls, "elapsed_s": turn.elapsed_s, "usage": turn.usage,
                             "changed_fields": [r["field"] for r in turn.proposal.changes] if turn.proposal else [],
                             "validation_success": turn.proposal is not None, "render_success": turn.proposal is not None,
                             "execution_success": turn.status == "applied", "samples_unchanged": True if turn.proposal else None})
        self.records = self.records[-200:]

    def export_records(self):
        return json.dumps(self.records, ensure_ascii=False, indent=2)

"""AI can edit drawing intent only; it cannot mutate manifests or execute code."""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator, TypeAdapter
from wavelab.domain.figure import FigureSpec, PanelSpec, SeriesSpec, EventSpec, PageSpec, LanguageSpec, TimeAxisSpec, LegendSpec, InsetSpec
from wavelab.app_preview import preview_png


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


KINDS = Literal["query_context", "set_page", "set_languages", "set_time_axis", "set_legend",
                "move_panel", "create_panel", "update_panel", "remove_panel", "add_series", "update_series",
                "remove_series", "move_series", "upsert_event", "remove_event", "undo", "redo",
                "create_inset", "update_inset", "remove_inset", "set_channel_properties"]


class Action(StrictModel):
    action: KINDS
    panel_id: str | None = None
    channel_id: str | None = None
    target_panel_id: str | None = None
    target_index: int | None = Field(default=None, ge=0)
    event_index: int | None = Field(default=None, ge=0)
    inset_id: str | None = Field(default=None, min_length=1)
    changes: dict[str, JsonValue] = Field(default_factory=dict)
    evidence_quote: str | None = None


class Plan(StrictModel):
    summary: str = Field(min_length=1, max_length=3000)
    clarification: str | None = Field(default=None, max_length=3000)
    actions: list[Action] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def consistent(self):
        if self.clarification and self.actions:
            raise ValueError("澄清方案不能同时包含编辑操作")
        if not self.clarification and not self.actions:
            raise ValueError("方案必须包含操作或澄清问题")
        return self


class ChannelPropertiesPatch(StrictModel):
    display_name: str = Field(min_length=1)
    quantity_name: str
    unit: str | None = None


ALLOWED = {
    "set_channel_properties": {"display_name", "quantity_name", "unit"},
    "set_page": {"preset", "width_in", "height_in", "font_size_pt", "axes_font_size_pt", "title_font_size_pt", "panel_spacing", "legend_spacing", "dpi", "font_family"},
    "set_languages": {"legend", "axes"},
    "set_time_axis": {"mode", "unit", "event_time_s", "xlim", "label_i18n"},
    "set_legend": {"location", "columns", "font_size_pt", "font_family"},
    "create_panel": {"title_i18n", "ylim", "xlim", "scientific_y", "plot_mode"},
    "update_panel": {"title_i18n", "ylim", "xlim", "scientific_y", "plot_mode"},
    "add_series": {"color", "linestyle", "linewidth_pt", "visible"},
    "update_series": {"color", "linestyle", "linewidth_pt", "visible"},
    "upsert_event": {"time_s", "label", "label_i18n", "color", "linestyle", "panel_ids"},
    "create_inset": {"channel_ids", "xlim_s", "ylim", "bounds", "show_region", "show_connectors"},
    "update_inset": {"channel_ids", "xlim_s", "ylim", "bounds", "show_region", "show_connectors"},
}
MODELS = {"set_channel_properties": ChannelPropertiesPatch, "set_page": PageSpec, "set_languages": LanguageSpec, "set_time_axis": TimeAxisSpec,
          "set_legend": LegendSpec, "create_panel": PanelSpec, "update_panel": PanelSpec,
          "add_series": SeriesSpec, "update_series": SeriesSpec, "upsert_event": EventSpec,
          "create_inset": InsetSpec, "update_inset": InsetSpec}
TARGETS = {
    "set_channel_properties": {"channel_id", "evidence_quote"},
    "move_panel": {"panel_id", "target_index"}, "create_panel": {"panel_id", "target_index"}, "update_panel": {"panel_id"}, "remove_panel": {"panel_id"},
    "add_series": {"panel_id", "channel_id"}, "update_series": {"panel_id", "channel_id"},
    "remove_series": {"panel_id", "channel_id"}, "move_series": {"panel_id", "channel_id", "target_panel_id"},
    "upsert_event": {"event_index", "evidence_quote"}, "remove_event": {"event_index"},
    "set_time_axis": {"evidence_quote"},
    "create_inset": {"panel_id", "inset_id"}, "update_inset": {"panel_id", "inset_id"},
    "remove_inset": {"panel_id", "inset_id"},
}


def tool_definitions():
    definitions = {"response_schema": Plan.model_json_schema(), "allowed_changes": {k: sorted(v) for k, v in ALLOWED.items()},
            "rules": "panels container order is display order; IDs are stable identities. move_panel requires panel_id and target_index (zero-based final position, 0..N-1). create_panel optionally accepts target_index (0..N, default append). Actions execute sequentially against the updated list. Use panel_id and channel_id for series; move_series also needs target_panel_id. Event indices are zero based; omit index to append. Changes are partial patches. xlim uses DISPLAY units. Time mode/unit changes preserve the physical window unless xlim is explicitly supplied. Insets: create_inset/update_inset/remove_inset require panel_id and inset_id; create requires a globally unique explicit inset_id and changes.xlim_s. update/remove require an existing inset in that panel. xlim_s is ALWAYS absolute source seconds, even on relative/ms axes; convert user display coordinates using the current origin and unit. bounds=[left,bottom,width,height] are parent-axes fractions and must fit inside [0,1]. Empty channel_ids inherits visible parent series; explicit channel_ids must belong to the parent. ylim=null restores automatic limits. Styles inherit parent lines. Do not infer event times to convert relative windows. Use set_channel_properties for source metadata; physical mappings remain protected. No code, files, network or waveform operations. Event time/origin needs existing confirmed event or verbatim evidence_quote from user request containing explicit seconds (s/秒). query_context returns the provided metadata. undo/redo must be the only action."}


    definitions["rules"] += " Channel names, quantities and source units have one authority in datasets. Legends and Y axes are automatic. Use set_channel_properties only; independent series labels and Y axis quantity/display-unit patches are no longer supported. Same-quantity mixed SI units may be converted in display arrays automatically; mixed quantities or unconvertible units produce a warning and never block source metadata saves."
    from dataclasses import asdict
    definitions["rules"] += " Panel plot_mode is analog (default) or digital_tracks: unitless finite binary 0/1 channels, separate lanes in visible series order, first at top, steps-post; lane offsets affect drawing only, including insets. Nonbinary data rejects the transaction."
    from wavelab.quantity_presets import QUANTITY_PRESETS
    definitions["quantity_presets"] = [dict(asdict(q),units=list(q.units)) for q in QUANTITY_PRESETS.values()]
    definitions["rules"] += " set_channel_properties requires channel_id; partial changes display_name, quantity_name (preset ID/name or custom text; empty clears), unit (source unit; null clears). Nonempty source unit requires evidence_quote containing that unit verbatim in user_request. Metadata only; no sample conversion. Batch multiple channels atomically. Custom quantity text uses the same name in both languages. No curve/axis metadata overrides are persisted. Mixed panels warn and still allow metadata saves."
    return definitions


def merge(target, changes):
    for key, value in changes.items():
        if key.endswith("_i18n"):
            if not isinstance(value, dict) or not set(value) <= {"zh", "en"}:
                raise ValueError("双语标签只允许 zh/en 字段")
            target[key].update(value)
        else:
            target[key] = deepcopy(value)


def diff(before, after, path=""):
    """Leaf-level changes, including additions/removals; no source metadata."""
    if isinstance(before, dict) and isinstance(after, dict):
        rows = []
        for key in sorted(set(before) | set(after)):
            rows += diff(before.get(key), after.get(key), f"{path}.{key}".strip("."))
        return rows
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [r for i, (a, b) in enumerate(zip(before, after)) for r in diff(a, b, f"{path}[{i}]")]
    return [] if before == after else [{"field": path, "before": before, "after": after}]


def fingerprint(spec):
    return hashlib.sha256(spec.model_dump_json().encode()).hexdigest()


def sample_hashes(w):
    return {key: hashlib.sha256(data.samples.tobytes()).hexdigest() for key, data in w.datasets.items()}


def require_time(value, action, request, spec):
    if value in [e.time_s for e in spec.events]:
        return
    quote = action.evidence_quote
    if not quote or quote not in request:
        raise ValueError("事件时刻未确认：需要用户原话中的明确秒值，或现有确认事件")
    values = [float(m) for m in re.findall(r"(?<![\d.])([+-]?\d+(?:\.\d+)?)\s*(?:秒|seconds?\b|s\b)", quote)]
    if value not in values:
        raise ValueError("事件时刻与用户提供的秒值不符；请明确提供事件时刻")


def build(w, plan, request):
    payload = w.spec.model_dump(mode="json")
    channels = {c.channel_id: c for m in w.spec.datasets for c in m.channels}
    writes = {}
    touched_insets = set()
    def panel(pid):
        result = next((p for p in payload["panels"] if p["id"] == pid), None)
        if result is None:
            raise ValueError(f"不存在的子图: {pid}")
        return result
    for a in plan.actions:
        kind = a.action
        allowed_targets = TARGETS.get(kind, set())
        if any(getattr(a, key) is not None for key in {"panel_id", "channel_id", "target_panel_id", "event_index", "evidence_quote", "target_index", "inset_id"} - allowed_targets):
            raise ValueError(f"{kind}: 不允许的目标参数")
        if not set(a.changes) <= ALLOWED.get(kind, set()):
            raise ValueError(f"{kind}: 不允许的修改字段")
        for key, value in a.changes.items():
            TypeAdapter(MODELS[kind].model_fields[key].annotation).validate_json(json.dumps(value), strict=True)
            target_key = (kind.replace("add_", "update_").replace("create_", "update_"), a.panel_id, a.channel_id, a.event_index, a.inset_id, key)
            if target_key in writes and writes[target_key] != value:
                raise ValueError(f"同一事务包含冲突修改: {key}")
            writes[target_key] = value
        if kind in {"undo", "redo"}:
            if len(plan.actions) != 1:
                raise ValueError("撤销/恢复必须独立提交")
            stack = w.undo_stack if kind == "undo" else w.redo_stack
            if not stack:
                raise ValueError("没有可撤销/恢复的操作")
            return stack[-1]
        if kind == "query_context":
            continue
        if kind == "set_channel_properties":
            from wavelab.channel_properties import patch_channels
            from wavelab.quantity_presets import QuantityLibrary
            unit = a.changes.get("unit")
            if unit and (not a.evidence_quote or a.evidence_quote not in request or not re.search(r"(?<![A-Za-zµμ])" + re.escape(unit) + r"(?![A-Za-z])", a.evidence_quote)):
                raise ValueError("源单位需要用户原话明确确认")
            patch_channels(payload, {a.channel_id: a.changes}, QuantityLibrary(w.root).presets(),
                           "用户明确确认通道属性（不换算采样值）")
        elif kind.startswith("set_"):
            name = kind[4:]
            target = payload[name]
            if name == "time_axis":
                old = deepcopy(target)
                if "event_time_s" in a.changes and a.changes["event_time_s"] is not None:
                    require_time(a.changes["event_time_s"], a, request, w.spec)
                merge(target, a.changes)
                if target["mode"] == "absolute" and "event_time_s" not in a.changes:
                    target["event_time_s"] = None
                if (old["mode"], old["unit"], old["event_time_s"]) != (target["mode"], target["unit"], target["event_time_s"]):
                    if target["mode"] == "relative" and target["event_time_s"] is not None:
                        require_time(target["event_time_s"], a, request, w.spec)
                    def convert(limits):
                        if limits is None:
                            return None
                        from wavelab.quantity_presets import time_factor
                        return [(v / time_factor(old["unit"]) + (old["event_time_s"] or 0) - (target["event_time_s"] or 0)) * time_factor(target["unit"]) for v in limits]
                    if "xlim" not in a.changes:
                        target["xlim"] = convert(old["xlim"])
                    for p in payload["panels"]:
                        p["xlim"] = convert(p["xlim"])
                if "xlim" in a.changes and payload["share_time_axis"]:
                    for p in payload["panels"]:
                        p["xlim"] = None
            else:
                merge(target, a.changes)
                if name == "page" and a.changes.get("preset") in {"ieee_single_column", "ieee_double_column"}:
                    target["width_in"] = None
                if name == "languages":
                    if payload["page"]["font_family"] in {"SimSun", "Times New Roman"}:
                        payload["page"]["font_family"] = "SimSun" if target["axes"] == "zh" else "Times New Roman"
                    if payload["legend"]["font_family"] in {None, "SimSun", "Times New Roman"}:
                        payload["legend"]["font_family"] = "SimSun" if target["legend"] == "zh" else "Times New Roman"
        elif kind == "create_panel":
            if not a.panel_id or any(p["id"] == a.panel_id for p in payload["panels"]):
                raise ValueError("新子图需要唯一 panel_id")
            p = PanelSpec(id=a.panel_id).model_dump(mode="json")
            merge(p, a.changes)
            index = len(payload["panels"]) if a.target_index is None else a.target_index
            if index > len(payload["panels"]):
                raise ValueError("插入位置越界")
            payload["panels"].insert(index, p)
        elif kind == "move_panel":
            p = panel(a.panel_id)
            if a.target_index is None or a.target_index >= len(payload["panels"]):
                raise ValueError("排序目标位置越界或缺失")
            payload["panels"].remove(p)
            payload["panels"].insert(a.target_index, p)
        elif kind == "update_panel":
            merge(panel(a.panel_id), a.changes)
        elif kind == "remove_panel":
            payload["panels"].remove(panel(a.panel_id))
            events = []
            for event in payload["events"]:
                if event["panel_ids"]:
                    event["panel_ids"] = [pid for pid in event["panel_ids"] if pid != a.panel_id]
                    if not event["panel_ids"]:
                        continue
                events.append(event)
            payload["events"] = events
        elif kind in {"add_series", "update_series", "remove_series", "move_series"}:
            if a.channel_id not in channels:
                raise ValueError(f"不存在的 channel_id: {a.channel_id}")
            p = panel(a.panel_id)
            s = next((s for s in p["series"] if s["channel_id"] == a.channel_id), None)
            if kind == "add_series":
                if s is not None:
                    raise ValueError("曲线已存在；请使用 update_series")
                c = channels[a.channel_id]
                s = SeriesSpec(channel_id=c.channel_id).model_dump(mode="json")
                p["series"].append(s)
                merge(s, a.changes)
            else:
                if s is None:
                    raise ValueError("目标曲线尚未添加")
                if kind == "update_series":
                    merge(s, a.changes)
                else:
                    p["series"].remove(s)
                    if kind == "move_series":
                        panel(a.target_panel_id)["series"].append(s)
        elif kind in {"create_inset", "update_inset", "remove_inset"}:
            target = panel(a.panel_id)
            if not a.inset_id:
                raise ValueError("局部图操作需要明确 inset_id")
            existing = next((i for i in target["insets"] if i["id"] == a.inset_id), None)
            if kind == "create_inset":
                if any(i["id"] == a.inset_id for p in payload["panels"] for i in p["insets"]):
                    raise ValueError("新局部图需要全局唯一 inset_id")
                if "xlim_s" not in a.changes:
                    raise ValueError("新增局部图需要明确绝对秒范围 xlim_s")
                target["insets"].append(InsetSpec.model_validate(dict(id=a.inset_id, **a.changes)).model_dump(mode="json"))
            else:
                if existing is None:
                    raise ValueError(f"所属子图不存在局部图: {a.inset_id}")
                if kind == "remove_inset":
                    target["insets"].remove(existing)
                else:
                    merge(existing, a.changes)
            touched_insets.add((a.panel_id, a.inset_id))
        elif kind == "upsert_event":
            if a.event_index is None:
                if "time_s" not in a.changes or "label" not in a.changes:
                    raise ValueError("新增事件需要明确时刻和标签")
                event = EventSpec(time_s=a.changes["time_s"], label=a.changes["label"], confirmation_source="用户确认 AI 事件方案").model_dump(mode="json")
                require_time(event["time_s"], a, request, w.spec)
                payload["events"].append(event)
            else:
                if a.event_index >= len(payload["events"]):
                    raise ValueError("不存在的事件索引")
                event = payload["events"][a.event_index]
            if "time_s" in a.changes:
                require_time(a.changes["time_s"], a, request, w.spec)
                event["confirmation_source"] = "用户确认 AI 事件方案"
            merge(event, a.changes)
        elif kind == "remove_event":
            if a.event_index is None or a.event_index >= len(payload["events"]):
                raise ValueError("不存在的事件索引")
            payload["events"].pop(a.event_index)
    candidate = FigureSpec.model_validate(payload)
    from wavelab.render.insets import validate_inset
    for p in candidate.panels:
        for inset in p.insets:
            if (p.id, inset.id) in touched_insets:
                validate_inset(inset, p, w.datasets)
    return candidate


@dataclass(frozen=True)
class Proposal:
    revision: int
    base_fingerprint: str
    plan: Plan
    candidate: FigureSpec
    changes: list[dict]
    preview: bytes
    warnings: tuple[str, ...]
    data_hashes: dict[str, str]
    request: str


def candidate_views(w, candidate):
    return {m.dataset_id: w.datasets[m.dataset_id].with_manifest(m) for m in candidate.datasets}


def validate_manifest_edit(w, candidate, plan):
    if candidate.datasets == w.spec.datasets:
        return
    if not any(a.action in {"set_channel_properties", "undo", "redo"} for a in plan.actions):
        raise ValueError("AI 不得修改数据清单、单位或物理映射")
    def immutable(manifests):
        rows = [m.model_dump(mode="json") for m in manifests]
        for row in rows:
            for channel in row["channels"]:
                channel.pop("unit", None)
                channel.pop("quantity", None)
                if any(a.action == "set_channel_properties" for a in plan.actions):
                    channel.pop("display_name", None)
        return rows
    if immutable(candidate.datasets) != immutable(w.spec.datasets):
        raise ValueError("不得修改源文件、通道身份或物理映射")


def prepare(w, plan, request=""):
    if w.spec is None:
        raise ValueError("请先导入数据")
    if plan.clarification:
        raise ValueError(plan.clarification)
    revision, base = w.revision, fingerprint(w.spec)
    hashes = sample_hashes(w)
    candidate = build(w, plan, request)
    validate_manifest_edit(w, candidate, plan)
    from wavelab.mcp_metrics import measure
    with measure("render_ms"):
        image, warnings = preview_png(candidate, candidate_views(w, candidate))
    if hashes != sample_hashes(w):
        raise ValueError("原始样本完整性验证失败")
    if revision != w.revision or base != fingerprint(w.spec):
        raise ValueError("绘图状态已变化，请重新生成方案")
    return Proposal(revision, base, plan, candidate, diff(w.spec.model_dump(mode="json"), candidate.model_dump(mode="json")), image, warnings, hashes, request)


def apply_proposal(w, proposal):
    if w.revision != proposal.revision or fingerprint(w.spec) != proposal.base_fingerprint:
        raise ValueError("方案已过期：图形被手动编辑、撤销或重新打开，请重新生成")
    if proposal.data_hashes != sample_hashes(w):
        raise ValueError("原始样本完整性验证失败")
    # Revalidate/preview before mutation, even if an in-memory proposal was tampered with.
    candidate = FigureSpec.model_validate(proposal.candidate.model_dump())
    rebuilt = build(w, proposal.plan, proposal.request)
    if candidate != rebuilt or proposal.changes != diff(w.spec.model_dump(mode="json"), candidate.model_dump(mode="json")):
        raise ValueError("方案配置或差异与结构化操作不一致")
    validate_manifest_edit(w, candidate, proposal.plan)
    from wavelab.mcp_metrics import measure
    with measure("render_ms"):
        preview_png(candidate, candidate_views(w, candidate))
    if proposal.data_hashes != sample_hashes(w):
        raise ValueError("原始样本完整性验证失败")
    if len(proposal.plan.actions) == 1 and proposal.plan.actions[0].action in {"undo", "redo"}:
        kind = proposal.plan.actions[0].action
        stack = w.undo_stack if kind == "undo" else w.redo_stack
        if not stack or candidate != stack[-1]:
            raise ValueError("撤销/恢复目标不一致")
        getattr(w, kind)()
    else:
        w.commit(candidate.model_dump(mode="json"))
    return {"status": "applied", "revision": w.revision, "changes": proposal.changes, "render_success": True, "samples_unchanged": True}

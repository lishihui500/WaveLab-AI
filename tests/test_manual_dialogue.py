"""Local protocol regression; no external model generation is claimed."""
import json
import pytest
from test_manual import w, response, patch
from wavelab.ai.manual import ManualExchange
from wavelab.commands.plot import fingerprint


def test_two_phase_prompt_and_snapshot_export(w, tmp_path):
    e = ManualExchange()
    s = e.generate(w, "将两条曲线改为红色虚线，其余不变")
    document = json.loads(s.prompt.split("\n\n")[-1])
    for rule in ("阶段 A", "阶段 B", "不输出中间 JSON", "初始 user_request", "最新明确纠正", "唯一 display_name", "不持久化映射", "新快照", "不可信数据"):
        assert rule in s.prompt
    for obsolete in ("JSON only", "Return a JSON object", "actions=[]", "只返回一个符合"):
        assert obsolete not in s.prompt
    assert document["output_example"]["plan"]["clarification"] is None
    from wavelab.ai.manual import ManualResponse
    ManualResponse.model_validate(document["output_example"])
    target = tmp_path / "manual_request.txt"
    target.write_text(s.prompt, encoding="utf-8")
    assert target.read_text(encoding="utf-8") == s.prompt


def test_single_final_styles_without_physical_mapping(w):
    e = ManualExchange()
    from wavelab.workbench import Workbench
    w = Workbench(w.root / "unmapped")
    w.import_bytes(b"Domain,u,u\n0,1,2\n1,3,4\n2,5,6", "local.txt")
    w.assign_channels("panel_1", [c.channel_id for c in w.spec.datasets[0].channels])
    assert all(not c.physical_role for c in w.spec.datasets[0].channels)
    before = w.spec
    s = e.generate(w, "将两条曲线改为红色虚线，其余不变")
    actions = [dict(action="update_series", panel_id="panel_1", channel_id=x.channel_id,
                    changes={"color":"red", "linestyle":"--"}) for x in before.panels[0].series]
    e.validate(w, response(e, actions))
    assert e.snapshot is s and w.spec == before
    e.apply(w)
    assert all(x.color == "red" and x.linestyle == "--" for x in w.spec.panels[0].series)
    assert w.spec.datasets == before.datasets
    assert w.spec.time_axis == before.time_axis
    with pytest.raises(ValueError):
        e.validate(w, response(e, actions))
    e.generate(w, "下一任务")
    assert e.snapshot.request_id != s.request_id


def test_later_event_evidence_single_binding(w):
    e = ManualExchange(); s = e.generate(w, "将故障附近放大，使用相对毫秒")
    action = dict(action="set_time_axis", changes={"mode":"relative", "unit":"ms", "event_time_s":1.5, "xlim":[-2,4]}, evidence_quote="故障为 1.5 s")
    raw = response(e, [action])
    with pytest.raises(ValueError, match="事件"):
        e.validate(w, raw)
    e.validate(w, raw, confirmation="故障为 1.5 s；范围前2ms至后4ms")
    assert e.snapshot is s
    e.apply(w)
    assert w.spec.time_axis.event_time_s == 1.5


@pytest.mark.parametrize("after_preview", [False, True])
def test_unrelated_local_change_rejects_stale(w, after_preview):
    e = ManualExchange(); e.generate(w, "第一条改红色")
    raw = response(e, [patch(w, color="red")])
    if after_preview:
        e.validate(w, raw)
    w.update(["legend", "columns"], 2)
    before, rev, fp = w.spec, w.revision, fingerprint(w.spec)
    with pytest.raises(ValueError, match="过期"):
        e.apply(w) if after_preview else e.validate(w, raw)
    assert w.spec == before and w.revision == rev and fingerprint(w.spec) == fp


def test_corrected_target_only_changes_selected_series(w):
    e = ManualExchange(); s = e.generate(w, "将目标曲线设为红色虚线")
    before = w.spec
    target = before.panels[0].series[1].channel_id
    raw = response(e, [dict(action="update_series", panel_id="panel_1", channel_id=target,
                            changes={"color":"red", "linestyle":"--"})])
    e.validate(w, raw); e.apply(w)
    assert w.spec.panels[0].series[0] == before.panels[0].series[0]
    assert w.spec.panels[0].series[1].color == "red"
    assert e.snapshot is s

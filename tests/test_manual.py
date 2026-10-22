"""Scripted local JSON acceptance; no ChatGPT or model service calls."""
import json
from pathlib import Path
from typing import get_args

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from wavelab.workbench import Workbench
from wavelab.ai.manual import ManualExchange, ManualResponse, parse_response, protocol, compact_protocol
from wavelab.commands.plot import ALLOWED, MODELS, TARGETS, KINDS


@pytest.fixture
def w(tmp_path):
    w = Workbench(tmp_path)
    identity = w.import_bytes(b"Domain,u,u\n0,1,2\n1,3,4\n2,5,6", "PRIVATE_FILE.txt")
    w.map_channels(identity, "u", "numbered", "PRIVATE_CONFIRMATION", "kV")
    w.assign_channels("panel_1", [c.channel_id for c in w.spec.datasets[0].channels])
    return w


def response(e, actions=None, clarification=None):
    s = e.snapshot
    return json.dumps(dict(request_id=s.request_id, revision=s.revision, fingerprint=s.fingerprint,
                           plan=dict(summary="测试候选修改", clarification=clarification,
                                     actions=actions if actions is not None else [{"action": "set_legend", "changes": {"columns": 2}}])), ensure_ascii=False)


def patch(w, **changes):
    return dict(action="update_series", panel_id="panel_1", channel_id=w.spec.panels[0].series[0].channel_id, changes=changes)


def test_request_privacy_protocol_and_current_state(w):
    e = ManualExchange()
    s = e.generate(w, "只改变图例列数")
    for secret in ["PRIVATE_FILE", "PRIVATE_CONFIRMATION", str(w.root), "source_path", "source_sha256", "raw_headers", '"samples"']:
        assert secret not in s.prompt
    document = json.loads(s.prompt.split("\n\n")[-1])
    assert document["user_request"] == s.request
    assert document["binding"]["revision"] == w.revision
    assert document["protocol"] == compact_protocol()
    assert document["figure_context"]["panels"][0]["series"][0]["channel_id"] == w.spec.panels[0].series[0].channel_id
    assert document["protocol"]["output_schema"] == ManualResponse.model_json_schema()
    assert set(document["protocol"]["output_schema"]["$defs"]["Action"]["properties"]["action"]["enum"]) == set(get_args(KINDS))
    assert document["protocol"]["targets_by_action"] == {k: sorted(v) for k,v in TARGETS.items()}
    for kind, names in ALLOWED.items():
        assert set(document["protocol"]["patch_schema_by_action"][kind]) == names
    assert document["protocol"]["patch_schema_by_action"]["set_page"]["dpi"]["minimum"] == 72


@pytest.mark.parametrize("fenced", [False, True])
def test_valid_import_preview_and_explicit_apply(w, fenced):
    e = ManualExchange()
    e.generate(w, "第一条曲线红色虚线")
    before = w.spec
    raw = response(e, [patch(w, color="red", linestyle="--")])
    p = e.validate(w, "```json\n"+raw+"\n```" if fenced else raw, source="scripted_json")
    assert w.spec == before and p.preview.startswith(b"\x89PNG")
    assert {r["field"] for r in p.changes} == {"panels[0].series[0].color", "panels[0].series[0].linestyle"}
    e.apply(w)
    assert w.spec.panels[0].series[1] == before.panels[0].series[1]
    assert e.records[-1]["execution_success"] and e.records[-1]["model_calls"] == 0
    assert not e.records[-1]["model_generation_verified"]
    w.undo()
    assert w.spec == before
    w.redo()
    assert w.spec.panels[0].series[0].color == "red"


@pytest.mark.parametrize("raw", ["", "not json", "[]", "{}", '{"request_id":1}',
                                      '```python\nprint(1)\n```', 'text\n```json\n{}\n```',
                                      '{"revision":1,"revision":2}', pytest.param('x'*250001,id='oversize')])
def test_bad_json(w, raw):
    e = ManualExchange(); e.generate(w,"测试")
    before = w.spec
    with pytest.raises(ValueError): e.validate(w, raw)
    assert w.spec == before and e.proposal is None


@pytest.mark.parametrize("action", [
    dict(action="update_panel",panel_id="missing",changes={"ylim":[0,1]}),
    dict(action="update_series",panel_id="panel_1",channel_id="missing:col_1",changes={"color":"red"}),
    dict(action="set_page",changes={"dpi":"300"}),
    dict(action="set_time_axis",changes={"xlim":[2,1]}),
    dict(action="update_panel",panel_id="panel_1",changes={"ylabel_i18n":{"en":"Current (kA)"}}),
    dict(action="exec",changes={"code":"print(1)"}),
    dict(action="set_time_axis",changes={"mode":"relative","event_time_s":1.5}),
    dict(action="set_page",changes={"source_path":"bad"}),
])
def test_transaction_rolls_back_on_bad_action(w, action):
    e = ManualExchange(); e.generate(w,"只修改样式")
    before, revision, stack = w.spec, w.revision, list(w.undo_stack)
    samples = next(iter(w.datasets.values())).samples.copy()
    with pytest.raises(ValueError): e.validate(w, response(e,[patch(w,color="red"),action]))
    assert w.spec == before and w.revision == revision and w.undo_stack == stack
    np.testing.assert_array_equal(samples,next(iter(w.datasets.values())).samples)


@pytest.mark.parametrize("change", ["edit", "undo_redo", "reopen", "other_workbench", "tamper", "new_request"])
def test_export_binding_rejects_stale_and_forged(w, tmp_path, change):
    e = ManualExchange(); e.generate(w,"图例两列")
    raw = response(e)
    if change == "edit": w.update(["legend","columns"],3)
    elif change == "undo_redo": w.undo(); w.redo()
    elif change == "reopen": w.open_project(w.save_project("reopen"))
    elif change == "other_workbench":
        other = Workbench(tmp_path / "other"); other.open_project(w.save_project("other"))
        other.revision = w.revision; other.spec = w.spec
        w = other
    elif change == "tamper":
        obj = json.loads(raw); obj["request_id"] = "forged"; raw = json.dumps(obj)
    elif change == "new_request": e.generate(w,"新请求")
    if change == "edit":
        # Echoing today's revision/fingerprint cannot change the retained local base.
        from wavelab.commands.plot import fingerprint
        obj=json.loads(raw); obj.update(revision=w.revision,fingerprint=fingerprint(w.spec)); raw=json.dumps(obj)
    before=w.spec
    with pytest.raises(ValueError): e.validate(w, raw)
    assert w.spec == before


def test_apply_after_manual_edit_and_cancel(w):
    e=ManualExchange(); e.generate(w,"两列")
    e.validate(w,response(e)); w.update(["legend","columns"],3)
    with pytest.raises(ValueError): e.apply(w)
    e.generate(w,"两列"); raw=response(e); e.validate(w,raw); e.cancel()
    with pytest.raises(ValueError): e.apply(w)
    for _ in range(2):
        with pytest.raises(ValueError): e.validate(w,raw)


def test_three_rounds_event_evidence_save_reopen_export(w, tmp_path):
    e=ManualExchange(); original=next(iter(w.datasets.values())).samples.copy()
    e.generate(w,"第一条曲线红色"); e.validate(w,response(e,[patch(w,color="red")])); e.apply(w)
    w.update(["panels",0,"series",1,"linestyle"],":")
    e.generate(w,"英文轴配中文图例"); assert '"color": "red"' in e.snapshot.prompt
    e.validate(w,response(e,[dict(action="set_languages",changes={"axes":"en","legend":"zh"})])); e.apply(w)
    e.generate(w,"故障时刻为 1.5 s，相对毫秒，范围前后20ms")
    e.validate(w,response(e,[dict(action="set_time_axis",changes={"mode":"relative","unit":"ms","event_time_s":1.5,"xlim":[-20,20]},evidence_quote="故障时刻为 1.5 s")])); e.apply(w)
    assert w.spec.panels[0].series[0].color=="red" and w.spec.panels[0].series[1].linestyle==":"
    saved=w.save_project("rounds"); other=Workbench(tmp_path / "restored"); other.open_project(saved)
    assert other.spec.panels==w.spec.panels and other.spec.languages==w.spec.languages and other.spec.time_axis==w.spec.time_axis
    np.testing.assert_array_equal(original,next(iter(other.datasets.values())).samples)
    paths,_=other.export("rounds",formats=("pdf","png","svg"),bilingual=True)
    assert len(paths)==6 and all(p.exists() and p.stat().st_size>0 for p in paths)


def test_clarification_not_edit_and_no_unconfirmed_roles(w):
    e=ManualExchange(); e.generate(w,"设故障时刻")
    assert e.validate(w,response(e,[],"请提供秒值")) is None
    assert e.status=="clarification"
    e.generate(w,"设第一条标签")
    with pytest.raises(ValueError,match="不允许"):
        e.validate(w,response(e,[patch(w,label_i18n={"zh":"A相上桥臂"})]))


def test_no_request_and_unknown_fields(w):
    e=ManualExchange()
    with pytest.raises(ValueError): e.validate(w,"{}")
    with pytest.raises(ValueError): e.generate(w," ")
    e.generate(w,"图例")
    obj=json.loads(response(e)); obj["python"]="print(1)"
    with pytest.raises(ValueError): e.validate(w,json.dumps(obj))


def test_gui_manual_without_key_persistence_sync_cancel(w,monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    def forbidden(*args,**kwargs): raise AssertionError("Manual mode must not call a provider")
    monkeypatch.setattr("wavelab.ai.provider.OpenAICompatibleProvider.generate_actions",forbidden)
    at=AppTest.from_file(Path(__file__).resolve().parents[1]/"app.py",default_timeout=40)
    at.session_state["workbench"]=w
    def find(kind,label): return next(x for x in getattr(at,kind) if x.label==label)
    at.run(); find("checkbox","启用 AI 助手").check().run()
    assert find("selectbox","AI 工作模式").value=="ChatGPT 手动协作"
    assert not any(x.label=="模型名称" for x in at.text_input)
    find("text_area","自然语言绘图要求").input("只改第一条为红色虚线").run()
    find("button","生成 ChatGPT 请求").click().run()
    e=at.session_state["manual_exchange"]; s=e.snapshot
    raw=response(e,[patch(w,color="red",linestyle="--")])
    find("text_area","粘贴 ChatGPT 返回结果").input(raw).run()
    find("button","解析并验证方案").click().run()
    assert not at.exception and e.status=="proposed"
    at.run(); assert e.snapshot==s and find("text_area","粘贴 ChatGPT 返回结果").value==raw
    find("text_area","粘贴 ChatGPT 返回结果").input(raw+" ").run()
    assert find("button","确认应用协作方案").disabled
    find("text_area","粘贴 ChatGPT 返回结果").input(raw).run()
    find("button","确认应用协作方案").click().run()
    assert not at.exception and find("text_input","颜色（留空使用科研配色）").value=="red"
    assert find("selectbox","线型").value=="--"
    find("button","撤销").click().run(); find("button","恢复").click().run()
    find("button","生成 ChatGPT 请求").click().run()
    find("text_area","粘贴 ChatGPT 返回结果").input(response(e)).run()
    find("button","解析并验证方案").click().run()
    find("button","取消协作方案").click().run()
    assert not at.exception and e.status=="cancelled" and w.spec.panels[0].series[0].color=="red"
    draft=find("text_area","粘贴 ChatGPT 返回结果").value
    find("selectbox","AI 工作模式").select("Mock（测试）").run()
    find("selectbox","AI 工作模式").select("ChatGPT 手动协作").run()
    assert find("text_area","粘贴 ChatGPT 返回结果").value==draft
    assert find("text_area","自然语言绘图要求").value=="只改第一条为红色虚线"
    assert not at.exception

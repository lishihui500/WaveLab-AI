"""Four private datasets; identical deterministic rubric for scripted/real plans.

Mock demonstrates command execution only. --real requires explicit consent and key.
No research waveforms are sent; detailed records stay in ignored reports/.
"""
import argparse
import hashlib
import json
from pathlib import Path
import os
import sys
from time import perf_counter

import numpy as np
from wavelab.ai import Assistant, MockProvider, OpenAICompatibleProvider
from wavelab.commands import Plan
from wavelab.commands.plot import diff
from wavelab.workbench import Workbench
from wavelab.render.engine import render_figure, export_figure

ROOT = Path(__file__).resolve().parents[1]


def a(kind, changes=None, **kw):
    return dict(action=kind, changes=changes or {}, **kw)


def p(*actions, clarification=None):
    return Plan(summary="验收脚本给定的结构化方案（Mock 不代表自然语言理解）", actions=list(actions), clarification=clarification)


def loaded(out, filename, six=False):
    w = Workbench(out / "workspace")
    source = ROOT / "test" / "fixtures" / filename
    cid = w.import_bytes(source.read_bytes(), filename)
    manifest = w.spec.datasets[0]
    if six:
        w.map_channels(cid, manifest.groups[0].group_name, "six_arms", "WaveLab_AI_Handoff.md 3.1 用户确认测试集1顺序", "kV")
    else:
        # Units below are explicitly supplied by the handoff for these voltage/current samples.
        unit = "kA" if "故障电流" in filename else "kV"
        w.edit_channels(cid, {c.channel_id: {"unit": unit} for c in manifest.channels})
    return w


def tasks(out):
    six = loaded(out, "测试集1.txt", True)
    ids = [c.channel_id for c in six.spec.datasets[0].channels]
    create = [a("update_panel", {"title_i18n": {"zh": "A相", "en": "Phase A"}, "ylabel_i18n": {"zh": "电容电压和 (kV)", "en": "Capacitor voltage sum (kV)"}}, panel_id="panel_1")]
    for phase in ("B", "C"):
        create.append(a("create_panel", {"title_i18n": {"zh": phase + "相", "en": "Phase " + phase}, "ylabel_i18n": {"zh": "电容电压和 (kV)", "en": "Capacitor voltage sum (kV)"}}, panel_id="panel_" + str(ord(phase)-64)))
    for i, cid in enumerate(ids):
        phase, arm = chr(65+i//2), "upper" if i%2 == 0 else "lower"
        create.append(a("add_series", {"color": "#1f77b4" if i%2 == 0 else "#ff7f0e", "linestyle": "-" if i%2 == 0 else "--", "label_i18n": {"zh": phase + "相" + ("上" if i%2 == 0 else "下") + "桥臂", "en": phase + " " + arm + " arm"}}, panel_id="panel_" + str(i//2+1), channel_id=cid))
    create += [a("set_page", {"preset": "ieee_double_column"}), a("set_languages", {"axes": "en", "legend": "en"})]
    def six_rubric(before, after):
        assert len(after.panels) == 3 and after.page.width == 7.16
        assert after.languages.axes == after.languages.legend == "en"
        for i, panel in enumerate(after.panels):
            assert [s.channel_id for s in panel.series] == ids[i*2:i*2+2]
            assert [s.linestyle for s in panel.series] == ["-", "--"]
            assert [s.color for s in panel.series] == ["#1f77b4", "#ff7f0e"]
            assert all(s.label_i18n.en for s in panel.series)
    yield "01_six_arms", six, "将已确认的六桥臂电容电压按 A、B、C 相放在三个纵向子图中，上桥臂蓝色实线、下桥臂橙色虚线，IEEE 双栏，图例和坐标轴英文。", p(*create), six_rubric

    def only(prefixes, check):
        def rubric(before, after):
            changes = diff(before.model_dump(mode="json"), after.model_dump(mode="json"))
            assert all(any(row["field"].startswith(prefix) for prefix in prefixes) for row in changes), changes
            check(after)
        return rubric
    yield "02_time_window", six, "将横轴范围调整为 1.4～1.6 秒，其他设置不变。", p(a("set_time_axis", {"xlim": [1.4, 1.6]})), only(["time_axis.xlim"], lambda s: require(s.time_axis.xlim == (1.4,1.6)))
    yield "03_mixed_languages", six, "把图例改成中文，坐标轴保持英文，其他设置不变。", p(a("set_languages", {"legend": "zh"})), only(["languages.legend", "legend.font_family"], lambda s: require(s.languages.legend == "zh" and s.languages.axes == "en"))
    before_style = six.spec  # Evaluated after the preceding generator yield has executed.
    yield "04_local_style", six, "只把 B 相下桥臂改为红色虚线，其他曲线和设置不变。", p(a("update_series", {"color": "red", "linestyle": "--"}, panel_id="panel_2", channel_id=ids[3])), only(["panels[1].series[1].color", "panels[1].series[1].linestyle"], lambda s: require(s.panels[1].series[1].color in {"red", "#ff0000", "#FF0000"} and s.panels[1].series[1].linestyle == "--"))
    yield "05_undo", six, "撤销刚才 B 相曲线的样式修改。", p(a("undo")), lambda b,s: require(s == before_style)
    if six.spec.panels[0].series:
        six.update(["panels",0,"series",0,"color"], "#228833")
    six.update(["page","preset"], "ieee_single_column")
    yield "06_gui_then_ai", six, "将当前图改为 IEEE 双栏，其余设置不变，包括手动设置的颜色。", p(a("set_page", {"preset":"ieee_double_column"})), only(["page.preset", "page.width_in"], lambda s: require(s.page.preset == "ieee_double_column" and s.panels[0].series[0].color == "#228833"))

    fault = loaded(out, "X相下桥臂故障电流.txt")
    ids_f = [c.channel_id for c in fault.spec.datasets[0].channels]
    fault_actions = [a("add_series", panel_id="panel_1", channel_id=cid) for cid in ids_f]
    fault_actions += [a("update_panel", {"ylabel_i18n": {"zh":"电流 (kA)","en":"Current (kA)"}}, panel_id="panel_1"), a("upsert_event", {"time_s":1.2,"label":"故障时刻", "label_i18n":{"zh":"故障时刻","en":"Fault inception"}}, evidence_quote="在 1.2 秒标记故障时刻"), a("set_time_axis", {"mode":"relative","unit":"ms","event_time_s":1.2}, evidence_quote="在 1.2 秒标记故障时刻"), a("set_legend", {"location":"outside_top"})]
    def fault_check(b,s):
        assert [x.channel_id for x in s.panels[0].series] == ids_f
        assert s.events[0].time_s == s.time_axis.event_time_s == 1.2 and s.time_axis.unit == "ms" and s.time_axis.mode == "relative"
        assert s.legend.location == "outside_top"
        result = render_figure(s, fault.datasets)
        try:
            np.testing.assert_array_equal(next(iter(result.lines.values())).get_xdata(), (next(iter(fault.datasets.values())).time_s - 1.2)*1000)
        finally:
            result.figure.clear()
    yield "07_fault_relative", fault, "绘制当前四条电流曲线，在 1.2 秒标记故障时刻，横轴改为相对故障时刻的 ms，图例放在图外上方。", p(*fault_actions), fault_check

    cap = loaded(out, "Full_Ucap.txt")
    ids_c = [c.channel_id for c in cap.spec.datasets[0].channels]
    yield "08_six_legend", cap, "六个电压通道按原始列序画在一张图中，Y 标题为电压 (kV)，图例放在图外上方，分成三列。", p(*[a("add_series", panel_id="panel_1", channel_id=cid) for cid in ids_c], a("set_legend",{"location":"outside_top","columns":3}), a("update_panel", {"ylabel_i18n":{"zh":"电压 (kV)","en":"Voltage (kV)"}}, panel_id="panel_1")), lambda b,s: require(len(s.panels)==1 and [x.channel_id for x in s.panels[0].series]==ids_c and s.legend.location=="outside_top" and s.legend.columns==3)
    yield "09_hide", cap, "只隐藏源列 2 的曲线，其他设置不变。", p(a("update_series", {"visible":False}, panel_id="panel_1",channel_id=ids_c[1])), only(["panels[0].series[1].visible"], lambda s: require(not s.panels[0].series[1].visible))
    yield "10_delete", cap, "删除源列 6 的曲线，保留其他曲线和属性。", p(a("remove_series",panel_id="panel_1",channel_id=ids_c[5])), lambda b,s: require(s.panels[0].series==b.panels[0].series[:5] and s.model_copy(update={"panels": b.panels})==b)

    large = loaded(out, "测试集2.txt")
    ids_l = [c.channel_id for c in large.spec.datasets[0].channels]
    yield "11_unconfirmed_numbered", large, "把当前五个电压通道按原始列序加入一张图，保留原始通道名称，不指定相别；IEEE 单栏、中文图例和中文轴标题电压 (kV)。", p(*[a("add_series",panel_id="panel_1",channel_id=cid) for cid in ids_l],a("set_page",{"preset":"ieee_single_column"}),a("set_languages",{"legend":"zh","axes":"zh"}),a("update_panel",{"ylabel_i18n":{"zh":"电压 (kV)"}},panel_id="panel_1")), lambda b,s: require([x.channel_id for x in s.panels[0].series]==ids_l and all(x.physical_role is None for x in s.panels[0].series) and s.page.preset=="ieee_single_column")
    yield "12_clarify_fault", large, "把故障时刻标出来。", p(clarification="请指定或确认故障时刻，单位为秒。"), lambda b,s: require(s==b)


def require(condition):
    if not condition:
        raise AssertionError("验收条件不满足")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--consent-metadata-and-cost", action="store_true", help="Explicit consent to send allowlisted metadata/history and incur API costs; also applies candidate plans in this isolated acceptance workspace")
    parser.add_argument("--model", default=os.environ.get("WAVELAB_AI_MODEL", ""))
    parser.add_argument("--base-url", default=os.environ.get("WAVELAB_AI_BASE_URL", "https://api.openai.com/v1"))
    args = parser.parse_args()
    if args.real and not (args.consent_metadata_and_cost and args.model and os.environ.get("OPENAI_API_KEY")):
        print("真实验收未运行：需要元数据/费用授权、模型名称及 OPENAI_API_KEY。没有发送工程数据。")
        return 2
    mode = "real" if args.real else "mock"
    out = ROOT / "reports" / "stage_03B" / mode
    out.mkdir(parents=True, exist_ok=True)
    original = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/"test"/"fixtures").glob("*.txt")}
    rows, assistants, works = [], {}, {}
    real = OpenAICompatibleProvider(model=args.model, base_url=args.base_url) if args.real else None
    for name, w, request, expected, rubric in tasks(out):
        assistant = assistants.setdefault(id(w), Assistant())
        works[id(w)] = w
        provider = real or MockProvider([expected])
        before = w.spec
        turn = assistant.propose(w, provider, request, consent=True, max_repairs=1 if args.real else 0)
        if turn.proposal:
            (out / (name + "_preview.png")).write_bytes(turn.proposal.preview)
        row = {"task":name,"mode":mode,"request":request,"model":turn.result.model if turn.result else args.model,"calls":turn.calls,"elapsed_s":turn.elapsed_s,"usage":turn.usage,"status":turn.status,"actions":turn.result.plan.model_dump(mode="json") if turn.result else None,"error":turn.error,"satisfied":False}
        try:
            if expected.clarification:
                assert turn.status=="clarification"
            else:
                assert turn.status=="proposed", turn.error
                # Independent rubric checks before committing, then rechecks actual result.
                rubric(before,turn.proposal.candidate)
                assistant.apply(w,turn)
            rubric(before,w.spec)
            row["satisfied"] = True
        except (AssertionError,ValueError,KeyError,IndexError) as exc:
            row["rubric_error"] = str(exc)
        row["status"] = turn.status
        row["changes"] = diff(before.model_dump(mode="json"),w.spec.model_dump(mode="json"))
        row["before"] = before.model_dump(mode="json")
        row["after"] = w.spec.model_dump(mode="json")
        rows.append(row)
        (out/"tasks.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"{name}: {mode}, {turn.status}, satisfied={row['satisfied']}, calls={turn.calls}, {turn.elapsed_s:.2f}s",flush=True)
    scenes = []
    for i,w in enumerate(works.values(),1):
        name=f"case_{i}"
        paths, warnings = w.export(name, bilingual=True)
        project=w.save_project(name)
        fresh=Workbench(out/"reopened")
        fresh.open_project(project)
        old=w.spec.model_dump(mode="json")
        new=fresh.spec.model_dump(mode="json")
        for obj in (old,new):
            for manifest in obj["datasets"]:
                manifest["source_path"]="<internal-data-copy>"
        assert old==new
        for key in w.datasets:
            np.testing.assert_array_equal(w.datasets[key].samples,fresh.datasets[key].samples)
        for path in paths:
            target=out/path.name
            target.write_bytes(path.read_bytes())
        scenes.append({"case":name,"project":str(project),"warnings":warnings,"reopen_equal":True,"files":[p.name for p in paths]})
    current={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/"test"/"fixtures").glob("*.txt")}
    assert original==current and len(original)==6
    summary={"mode":mode,"tasks":len(rows),"satisfied":sum(r["satisfied"] for r in rows),"source_hashes_before":original,"source_hashes_after":current,"source_unchanged":True,"cases":scenes,"model_calls":sum(r["calls"] for r in rows),"total_elapsed_s":sum(r["elapsed_s"] for r in rows),"real_model_verified":args.real and all(r["satisfied"] for r in rows),"cost":None,"comparison_results":None}
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in {"source_hashes_before","source_hashes_after","cases"}},ensure_ascii=False))
    return 0 if all(r["satisfied"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())

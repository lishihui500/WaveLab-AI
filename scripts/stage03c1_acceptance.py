"""Local scripted JSON acceptance. Never calls a model or transmits research data."""
import hashlib
import json
from pathlib import Path

import numpy as np

from wavelab.ai.manual import ManualExchange
from wavelab.commands.plot import sample_hashes
from wavelab.workbench import Workbench

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "stage_03C1"


def synthetic_csv():
    t = np.linspace(1.3, 1.7, 401)
    rows = ["Domain," + ",".join(["SyntheticArm"] * 6)]
    for x in t:
        values = [1 + .03*np.sin(2*np.pi*50*x + i*np.pi/3) for i in range(6)]
        rows.append(",".join([f"{x:.6f}"] + [f"{v:.9f}" for v in values]))
    return ("\n".join(rows)+"\n").encode()


def envelope(exchange, actions):
    s = exchange.snapshot
    return json.dumps(dict(request_id=s.request_id, revision=s.revision, fingerprint=s.fingerprint,
                           plan=dict(summary="脚本构造的本地验收候选", clarification=None, actions=actions)), ensure_ascii=False, indent=2)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    demo = ROOT / "examples" / "stage03c1_demo"
    demo.mkdir(exist_ok=True)
    (demo / "synthetic_arms.csv").write_bytes(synthetic_csv())
    real = ROOT / "test" / "fixtures" / "测试集1.txt"
    before_hash = hashlib.sha256(real.read_bytes()).hexdigest()
    results = []
    for name, raw, group in [("synthetic", synthetic_csv(), "SyntheticArm"), ("pscad", real.read_bytes(), "Udc_cap_SC")]:
        folder = OUT / name
        folder.mkdir(parents=True, exist_ok=True)
        w = Workbench(folder / "workspace")
        identity = w.import_bytes(raw, name + ".csv")
        w.map_channels(identity, group, "six_arms", "合成案例定义顺序" if name == "synthetic" else "用户已确认测试集1六桥臂顺序", "kV")
        ids = [c.channel_id for c in w.spec.datasets[0].channels]
        w.assign_channels("panel_1", ids)
        w.update(["panels",0,"title_i18n"], {"zh": "合成数据 · 脚本JSON验收" if name=="synthetic" else "本地PSCAD · 脚本JSON验收", "en":"Synthetic / scripted JSON acceptance" if name=="synthetic" else "Local PSCAD / scripted JSON acceptance"})
        base_path = w.save_project("Browser_base")
        matrix_hashes = sample_hashes(w)
        exchange=ManualExchange()
        tasks = [
            ("六桥臂按ABC分为三个子图，上桥臂实线，下桥臂虚线", [
                {"action":"create_panel","panel_id":"panel_B"}, {"action":"create_panel","panel_id":"panel_C"},
                *[{"action":"move_series","panel_id":"panel_1","channel_id":ids[i],"target_panel_id":"panel_B" if i<4 else "panel_C"} for i in range(2,6)],
                *[{"action":"update_series","panel_id":"panel_1" if i<2 else "panel_B" if i<4 else "panel_C","channel_id":ids[i],"changes":{"linestyle":"-" if i%2==0 else "--"}} for i in range(6)]]),
            ("英文坐标轴，中文图例", [{"action":"set_languages","changes":{"axes":"en","legend":"zh"}}]),
            ("故障时刻为 1.5 s，相对毫秒，时间范围前后20ms", [{"action":"set_time_axis","changes":{"mode":"relative","unit":"ms","event_time_s":1.5,"xlim":[-20,20]},"evidence_quote":"故障时刻为 1.5 s"}])]
        for index,(request,actions) in enumerate(tasks,1):
            snapshot=exchange.generate(w,request)
            (folder/f"{index}_request.txt").write_text(snapshot.prompt,encoding="utf-8")
            raw_plan=envelope(exchange,actions)
            (folder/f"{index}_scripted_response.json").write_text(raw_plan,encoding="utf-8")
            before=w.spec
            proposal=exchange.validate(w,raw_plan,source="scripted_json")
            assert w.spec==before
            (folder/f"{index}_preview.png").write_bytes(proposal.preview)
            exchange.apply(w)
            applied=w.spec
            w.undo(); assert w.spec==before
            w.redo(); assert w.spec==applied
        assert [len(p.series) for p in w.spec.panels]==[2,2,2]
        assert w.spec.time_axis.xlim==(-20,20) and w.spec.languages.axes=="en"
        assert sample_hashes(w)==matrix_hashes
        final=w.save_project("Scripted_final")
        other=Workbench(folder/"restored"); other.open_project(final)
        assert other.spec.panels==w.spec.panels and other.spec.time_axis==w.spec.time_axis
        assert sample_hashes(other)==matrix_hashes
        paths,_=w.export("scripted_final")
        results.append(dict(case=name,source="scripted_json",model_calls=0,base_project=str(base_path),
                            final_project=str(final),records=exchange.records,export_paths=[str(p) for p in paths],
                            matrix_unchanged=True,reopen_equal=True))
    assert before_hash==hashlib.sha256(real.read_bytes()).hexdigest()
    (OUT/"scripted_acceptance.json").write_text(json.dumps(dict(results=results,pscad_source_unchanged=True,real_model_tested=False),ensure_ascii=False,indent=2),encoding="utf-8")
    print("2 local cases x 3 scripted JSON rounds passed; 0 model calls; source/matrix/reopen/export verified")


if __name__=="__main__": main()

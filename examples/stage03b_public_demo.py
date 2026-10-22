"""Synthetic public demonstration; scripted tools, no real LLM or research data."""
from pathlib import Path
import numpy as np
from wavelab.workbench import Workbench
from wavelab.commands import Plan, prepare, apply_proposal

ROOT = Path(__file__).resolve().parents[1]


def main():
    t = np.linspace(0, 2, 2001)
    rows = ["Domain,Demo1,Demo2"]
    rows += [f"{time:.6f},{np.sin(2*np.pi*3*time):.9f},{0.7*np.cos(2*np.pi*3*time):.9f}" for time in t]
    w = Workbench(ROOT / "reports" / "stage_03B" / "public_demo")
    identity = w.import_bytes("\n".join(rows).encode(), "synthetic-demo.csv")
    actions = [dict(action="add_series", panel_id="panel_1", channel_id=f"{identity}:col_{i}", changes={"color":color,"linestyle":style,"label_i18n":{"zh":f"合成信号 {i}","en":f"Synthetic signal {i}"}}) for i,color,style in [(1,"#0072B2","-"),(2,"#D55E00","--")]]
    actions += [dict(action="update_panel", panel_id="panel_1",changes={"title_i18n":{"zh":"合成数据 · 脚本工具演示","en":"Synthetic data / scripted tool demonstration"},"ylabel_i18n":{"zh":"幅值（任意单位）","en":"Amplitude (arbitrary units)"}}),dict(action="set_time_axis",changes={"xlim":[0,0.6]}),dict(action="set_page",changes={"preset":"ieee_single_column"})]
    apply_proposal(w,prepare(w,Plan(summary="合成信号的受限命令演示，未调用模型",actions=actions)))
    print(w.save_project("Synthetic_demo"))
    paths,_=w.export("synthetic_demo")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()

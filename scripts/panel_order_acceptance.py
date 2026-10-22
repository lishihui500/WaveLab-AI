"""Reproducible synthetic six-arm + five-channel acceptance; no model calls."""
import hashlib
import json
from pathlib import Path
from time import perf_counter
import numpy as np
from wavelab.workbench import Workbench
from wavelab.commands import Plan, prepare, apply_proposal
from wavelab.domain.figure import EventSpec
from wavelab.render.engine import render_figure, export_figure

root=Path(__file__).resolve().parents[1]/"reports"/"panel_order"/"example"
w=Workbench(root)
t=np.linspace(0,.1,501)
values=np.column_stack([t]+[np.sin(2*np.pi*50*t+i/3)+i for i in range(11)])
raw=("Domain,"+",".join(["arm"]*6+["voltage"]*5)+"\n"+"\n".join(",".join(map(str,row)) for row in values)).encode()
did=w.import_bytes(raw,"synthetic_order.txt")
w.map_channels(did,"arm","six_arms","Synthetic fixture explicitly defines A upper/lower, B upper/lower, C upper/lower","kV")
w.map_channels(did,"voltage","numbered","Synthetic voltage group","kV")
channels=[c.channel_id for c in w.spec.datasets[0].channels]
w.assign_channels("panel_1",channels[6:]);w.create_panel("panel_2",0);w.assign_channels("panel_2",channels[:6])
w.upsert_inset("panel_2",dict(id="zoom",xlim_s=[.02,.04],bounds=[.56,.52,.4,.4]))
w.update(["events"],[EventSpec(time_s=.05,label="synthetic event",confirmation_source="fixture",panel_ids=("panel_2",)).model_dump()])
(root/"initial.json").write_text(w.spec.model_dump_json(indent=2),encoding="utf-8")
five=w.spec.panels[1];data=w.datasets[did];sample_hash=hashlib.sha256(data.samples.tobytes()).hexdigest()
six=w.spec.panels[0].series
w.create_panel("panel_3");w.create_panel("panel_4")
for j,s in enumerate(six[2:]):w.move_series("panel_2",s.channel_id,"panel_3" if j<2 else "panel_4")
before=w.spec
start=perf_counter();w.move_panel("panel_1",3);elapsed=perf_counter()-start
assert [p.id for p in w.spec.panels]==["panel_2","panel_3","panel_4","panel_1"]
assert all(p is next(q for q in before.panels if q.id==p.id) for p in w.spec.panels)
assert w.spec.panels[-1]==five
manual=w.spec
w.undo();assert w.spec==before
w.redo();assert w.spec==manual
w.undo()
proposal=prepare(w,Plan(summary="Move original five-channel panel to bottom",actions=[dict(action="move_panel",panel_id="panel_1",target_index=3)]))
apply_proposal(w,proposal);assert w.spec==manual
path=w.save_project("ordered_case");other=Workbench(root/"reopened");other.open_project(path)
assert other.spec.panels==w.spec.panels
assert hashlib.sha256(data.samples.tobytes()).hexdigest()==sample_hash and w.datasets[did] is data
result=render_figure(w.spec,w.datasets)
assert list(result.axes)==[p.id for p in w.spec.panels]
result.figure.canvas.draw()
ys=[result.axes[p.id].get_position().y0 for p in w.spec.panels]
assert all(a>b for a,b in zip(ys,ys[1:]))
for fmt in ("pdf","svg","png"):export_figure(result,root/f"ordered_case.{fmt}")
summary=dict(initial=["panel_2:6","panel_1:5"],final=[f"{p.id}:{len(p.series)}" for p in w.spec.panels],local_move_seconds=elapsed,samples_unchanged=True,objects_reused=True,save_reopen=True,undo_redo=True,ai_mode="scripted protocol only; no model call",exports=["ordered_case.pdf","ordered_case.svg","ordered_case.png"])
(root/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps(summary,ensure_ascii=False))

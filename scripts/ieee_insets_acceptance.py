"""Local real-PSCAD acceptance; writes only agent-owned report outputs."""
from pathlib import Path
from time import perf_counter
import hashlib
import json
import numpy as np
from wavelab.workbench import Workbench
from wavelab.domain.figure import PanelSpec
from wavelab.render.engine import render_figure, export_figure

root=Path(__file__).resolve().parents[1]
out=root/"reports"/"ieee_insets"
out.mkdir(parents=True,exist_ok=True)
sources=list((root/"test"/"fixtures").glob("*.txt"))
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
records=[]
for filename in ("Full_Ucap.txt","测试集2.txt"):
    w=Workbench(out/("local_"+Path(filename).stem))
    w.import_bytes((root/"test"/"fixtures"/filename).read_bytes(),filename)
    channels=[c.channel_id for c in w.spec.datasets[0].channels]
    data=next(iter(w.datasets.values()));samples=data.samples.copy()
    panels=[]
    for i in range(0,len(channels),2):
        panels.append(PanelSpec(id=f"panel_{i//2+1}").model_dump())
    w.update(["panels"],panels)
    for i,p in enumerate(w.spec.panels): w.assign_channels(p.id,channels[i*2:i*2+2])
    # Explicit units are the documented fixture convention, never inferred from headers.
    for panel in w.spec.panels: w.confirm_panel_quantity(panel.id,"电压","Voltage","kV")
    times=data.time_s;lo=float(times[len(times)//6]);hi=float(times[len(times)//6+max(10,len(times)//100)])
    for i,panel in enumerate(w.spec.panels):
        w.upsert_inset(panel.id,dict(id=f"zoom_{i}",xlim_s=[lo,hi]))
    start=perf_counter();result=render_figure(w.spec,w.datasets);elapsed=perf_counter()-start
    for fmt in ("pdf","svg","png"): export_figure(result,out/(Path(filename).stem+"_insets."+fmt))
    saved=w.save_project("acceptance");other=Workbench(out/"reopen");other.open_project(saved)
    assert other.spec.panels==w.spec.panels
    assert len(result.inset_axes)==len(w.spec.panels)
    assert all("Layout:" not in note for note in result.warnings)
    np.testing.assert_array_equal(next(iter(w.datasets.values())).samples,samples)
    np.testing.assert_array_equal(next(iter(other.datasets.values())).samples,samples)
    records.append(dict(file=filename,samples=len(times),panels=len(panels),render_s=elapsed,warnings=result.warnings))
assert hashes=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
(out/"acceptance.json").write_text(json.dumps(dict(records=records,source_sha256=hashes,source_hashes_unchanged=True),ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(records,ensure_ascii=False,indent=2))

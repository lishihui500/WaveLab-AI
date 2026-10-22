"""Independent infrastructure deadline observer; not a global tool interceptor."""
import json,time,sys
from pathlib import Path
from stage04_infra_v2 import DispatchGate

release_path=Path(sys.argv[1]);r=json.loads(release_path.read_text(encoding='utf-8'))
remaining=r['released_monotonic_s']+r['budget_s']-time.monotonic()
if remaining<=0:raise SystemExit('release already expired')
gate=DispatchGate(release_path.parent/'supervision',remaining)
gate.release({k:True for k in ['independent_context','direct_tools','logging_ready','deadline_ready']})
gate.log('original_release',release=r,role='observer; actual tools guarded in executor')
done=release_path.parent/'execution_done.json'
try:
 while not gate.closed.wait(.05):
  if done.exists():
   gate.log('executor_done',evidence=str(done));break
finally:gate.finish()

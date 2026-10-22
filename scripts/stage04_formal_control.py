"""Experiment bookkeeping only. Never generates or executes plot/UI actions."""
from pathlib import Path
import argparse,json,time,datetime,hashlib,shutil,sys,platform,importlib.metadata
R=Path(__file__).resolve().parents[1];O=R/'reports/stage_04'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('operation',choices=['freeze','release','finish','elapsed','checkpoint','assemble']);p.add_argument('trial',nargs='?');p.add_argument('--actor');p.add_argument('--status',default='COMPLETED');a=p.parse_args()
if a.operation=='freeze':
 files=[O/'protocol.md',O/'tasks.json',O/'constraints.json',O/'schedule.json',R/'scripts/stage04_score.py',R/'scripts/stage04_accept.py',R/'scripts/stage04_formal_control.py',R/'scripts/stage04_formal_accept.py',R/'scripts/stage03f_validate.py',R/'tests/test_stage04_score.py']
 files += list((R/'src/wavelab').rglob('*.py'))
 env={'python':sys.version,'platform':platform.platform(),'libraries':{k:importlib.metadata.version(k) for k in ['streamlit','numpy','pydantic','matplotlib']},'service_url':'http://127.0.0.1:8538/','model':'same inherited model and reasoning; no override','context':'new actor fork_turns=none per trial','tool_transport':'identical literal broker both arms','timeout_s':300}
 dump(O/'formal_environment.json',env);files.append(O/'formal_environment.json')
 for folder in (O/'formal').iterdir():
  if folder.is_dir():files += [x for x in (folder/'baseline').rglob('*') if x.is_file()]
 manifest={'frozen_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'files':{str(x.relative_to(R)):sha(x) for x in files},'rounds':24,'seed':20261020,'status':'FROZEN_BEFORE_FIRST_TRIAL'}
 dump(O/'formal_freeze.json',manifest);print('FROZEN',len(files),'files')
else:
 folder=O/'formal'/a.trial
 if not folder.is_dir() or folder.parent!=O/'formal':raise SystemExit('unknown trial')
 if a.operation=='release':
  if (folder/'timing.json').exists():raise SystemExit('already released')
  dump(folder/'timing.json',{'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'start_wall_ms':int(time.time()*1000),'start_monotonic_ns':time.monotonic_ns(),'actor':a.actor,'fork_turns':'none','timeout_s':300});print('RELEASED',a.trial)
 elif a.operation=='elapsed':
  t=read(folder/'timing.json');print(round((time.monotonic_ns()-t['start_monotonic_ns'])/1e9,3))
 elif a.operation=='finish':
  t=read(folder/'timing.json');t.update(end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),end_wall_ms=int(time.time()*1000),end_monotonic_ns=time.monotonic_ns(),agent_status=a.status);t['task_s']=(t['end_monotonic_ns']-t['start_monotonic_ns'])/1e9;t['within_budget']=t['task_s']<=300;dump(folder/'timing.json',t);print(json.dumps(t))
 elif a.operation=='checkpoint':
  shutil.copy2(folder/'saved/project.json',folder/'rejected_project.json');print('CHECKPOINT_CAPTURED')
 elif a.operation=='assemble':
  rows=[read(x) for x in sorted((folder/'broker').glob('*.json'))]
  contexts=[v for v in rows if v.get('tool')=='get_figure_context'];applies=[v for v in rows if v.get('tool')=='apply_plot_actions']
  if contexts and applies:
   l={'before':contexts[0]['result'],'after':contexts[-1]['result'],'apply':{'args':applies[-1]['args'],'result':applies[-1]['result']}}
   def body(v):return json.loads(v['result']['content'][0]['text'])
   rejected=next((v for v in applies if body(v).get('error')=='validation_error'),None)
   if rejected:
    mid=next((v for v in contexts if v['end_ms']>rejected['end_ms']),None)
    if mid:l.update(rejected={'args':rejected['args'],'result':rejected['result']},intermediate=mid['result'],recovery={'args':applies[-1]['args'],'result':applies[-1]['result']})
   dump(folder/'live_mcp_log.json',l)
  print('ASSEMBLED')

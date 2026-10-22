"""Formal v2 bookkeeping and evidence adapters. Does not execute plotting actions."""
from pathlib import Path
import sys,json,time,datetime,hashlib,shutil,subprocess,platform,importlib.metadata
R=Path(__file__).resolve().parents[1];O=R/'reports/stage_04';B=O/'formal_v2'
sys.path.insert(0,str(R/'scripts'))
from stage04_infra_v2 import assemble,parse_result
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def prepare():
 B.mkdir(exist_ok=False)
 for name in ['protocol.md','raw_results.csv','formal_execution_status.json']:
  shutil.copy2(O/name,O/'history'/('pre_v2_'+name))
 schedule=read(O/'schedule.json');schedule['batch']='formal_v2'
 for row in schedule['schedule']:
  row['legacy_trial_id']=row['trial_id'];row['trial_id']+='_V2';row['project_name']='Stage04_V2_'+row['legacy_trial_id']
  d=B/row['trial_id'];d.mkdir();shutil.copytree(R/'reports/stage_03F/baselines/F02',d/'baseline');(d/'saved').mkdir();(d/'evidence').mkdir()
  link=R/'.wavelab/projects'/row['project_name']
  if link.exists():raise RuntimeError('alias already exists')
  subprocess.run(['powershell','-NoProfile','-Command',f"New-Item -ItemType Junction -Path '{link}' -Target '{d/'saved'}' | Out-Null"],check=True)
 dump(B/'schedule.json',schedule)
 dump(B/'status.json',{'batch':'formal_v2','planned':24,'started':0,'finished':0,'current':None,'legacy_attempt_preserved':True,'states':[{**r,'status':'NOT_STARTED'} for r in schedule['schedule']]})
def freeze():
 frozen=read(O/'formal_freeze.json')['files'];protected=read(O/'protected_manifest.json')
 if any(sha(R/p)!=h for p,h in frozen.items() if p!='reports\\stage_04\\protocol.md'):raise RuntimeError('legacy frozen implementation changed')
 if any(sha(R/p)!=h for p,h in protected.items()):raise RuntimeError('protected changed')
 env={'python':sys.version,'platform':platform.platform(),'libraries':{k:importlib.metadata.version(k) for k in ['streamlit','numpy','pydantic','matplotlib']},'url':'http://127.0.0.1:8538/','model':'same inherited model/reasoning; no override','context':'new fork_turns=none per trial','transport':'direct CUA and actual MCP, no root broker','timeout_s':300,'system_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'wall_ns':time.time_ns(),'monotonic_ns':time.monotonic_ns(),'clock_info':str(time.get_clock_info('monotonic')),'preflight_reference':'infrastructure_v2/readiness_report.md','global_interceptor':False,'inflight_cancel':False}
 dump(B/'environment.json',env)
 paths=[O/'protocol.md',O/'tasks.json',O/'constraints.json',O/'schedule.json',B/'schedule.json',B/'environment.json',O/'infrastructure_v2/dispatch_guard.js',B/'executor_bootstrap.md']
 paths+=list((R/'src/wavelab').rglob('*.py'))
 paths += [R/'scripts'/p for p in ['stage04_v2_control.py','stage04_infra_v2.py','stage04_infra_watch.py','stage04_score.py','stage04_accept.py','stage04_formal_accept.py','stage03f_validate.py']]
 paths += [p for p in B.glob('*/baseline/**/*') if p.is_file()]
 dump(B/'freeze.json',{'frozen_utc':env['system_utc'],'cohort':'24 new trials; legacy orchestration-deviated attempt retained separately','files':{str(p.relative_to(R)):sha(p) for p in paths},'seed':20261020,'timeout_s':300})
def release(d,actor):
 if (d/'release.json').exists():raise RuntimeError('already released')
 r={'released_unix_ms':int(time.time()*1000),'released_monotonic_s':time.monotonic(),'budget_s':300,'actor':actor,'context_fork':'none'};r['deadline_ms']=r['released_unix_ms']+300000
 dump(d/'release.json',r);task=d.name.split('_')[1];prompt=read(O/'tasks.json')['prompts'][task]
 dump(d/'task_input.json',{'full_task':prompt,'common_execution_requirements':(B/'executor_bootstrap.md').read_text(encoding='utf-8'),'release':r})
 status=read(B/'status.json');status['started']+=1;status['current']=d.name
 next(x for x in status['states'] if x['trial_id']==d.name).update(status='RUNNING',actor=actor)
 dump(B/'status.json',status);print(json.dumps(r))
def finish(d):
 r=read(d/'release.json');done=read(d/'execution_done.json') if (d/'execution_done.json').exists() else {'status':'MISSING_COMPLETION','end_ms':int(time.time()*1000)}
 sec=(done['end_ms']-r['released_unix_ms'])/1000;dump(d/'timing.json',{'task_s':sec,'budget_s':300,'within_budget':sec<=300,'agent_completion':done,'time_boundary':'release through model-declared actual save and GUI reopen; late returns retained','censored_s':min(sec,300),'status':'TIMEOUT' if sec>300 or done.get('status')=='TIMEOUT' else done['status']})
 s=read(B/'status.json');s['finished']+=1;s['current']=None;next(x for x in s['states'] if x['trial_id']==d.name).update(status=read(d/'timing.json')['status']);dump(B/'status.json',s)
def logs(d):
 rows=[]
 for p in sorted((d/'evidence').glob('*mcp*log*.json')):
  value=read(p);items=value if isinstance(value,list) else value.get('events',[])
  for x in items:
   if 'result' in x and 'tool' in x:rows.append({**x,'tool':x['tool'].split('__')[-1]})
 rows.sort(key=lambda x:x.get('startMs',x.get('start_ms',0)));a=assemble(rows);dump(d/'evidence/normalized_assembly.json',a)
 contexts=[x for x in rows if x['tool']=='get_figure_context' and parse_result(x['result']).get('body') and 'context' in parse_result(x['result'])['body']]
 applies=[x for x in rows if x['tool']=='apply_plot_actions']
 if contexts and applies:
  live={'before':contexts[0]['result'],'after':contexts[-1]['result'],'apply':{'args':applies[-1].get('args'),'result':applies[-1]['result']}}
  rejection=next((x for x in applies if (parse_result(x['result']).get('body') or {}).get('error')=='validation_error'),None)
  if rejection:
   mid=next((x for x in contexts if x.get('startMs',0)>rejection.get('endMs',0)),None)
   recovery=next((x for x in applies if x.get('startMs',0)>rejection.get('endMs',0) and (parse_result(x['result']).get('body') or {}).get('result',{}).get('status')=='applied'),None)
   if mid and recovery:live.update(rejected={'args':rejection.get('args'),'result':rejection['result']},intermediate=mid['result'],recovery={'args':recovery.get('args'),'result':recovery['result']})
  dump(d/'live_mcp_log.json',live)
 if d.name.startswith('GUI_T4') and (d/'evidence/rejection.json').exists():
  rejection=read(d/'evidence/rejection.json');p=B/'gui_operation_log.json';items=read(p) if p.exists() else [];items.append({'trial':d.name,'rejection_snapshot':rejection.get('rejection_snapshot','')});dump(p,items)
 print('ASSEMBLED',len(rows),'records')
if __name__=='__main__':
 op=sys.argv[1];d=B/sys.argv[2] if len(sys.argv)>2 else None
 if op=='prepare':prepare()
 elif op=='freeze':freeze()
 elif op=='release':release(d,sys.argv[3])
 elif op=='finish':finish(d)
 elif op=='logs':logs(d)

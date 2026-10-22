"""Finalize Pilot evidence, including real-session tool logs and negative controls."""
from pathlib import Path
import sys,json,copy,csv,hashlib,base64,datetime,shutil
ROOT=Path(__file__).resolve().parents[1];O=ROOT/'reports/stage_04';P=O/'pilot';sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'src'))
from stage04_score import score
from wavelab.workbench import Workbench

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
constraints=read(O/'constraints.json')['tasks'];tasks=read(O/'tasks.json')['prompts'];gui={r['trial']:r for r in read(P/'gui_operation_log.json')};results=[]
for folder in sorted(P.iterdir()):
 if not folder.is_dir() or not (folder/'acceptance/score.json').exists():continue
 trial=folder.name;task=trial.split('_')[1];a=folder/'acceptance';e=read(a/'evidence.json');review=read(a/'visual_review.json') if (a/'visual_review.json').exists() else {};e['visual_review']=review.get('result')=='PASS_LEGIBILITY' and all(sha(a/n)==review.get('reviewed_sha256',{}).get(n) for n in ['final.png','final_pdf.png','after.json'])
 b=read(a/'before.json');f=read(a/('canonical_after.json' if (a/'canonical_after.json').exists() else 'after.json'));s=score(b,f,constraints[task],e,task_id=task)
 dump(a/'evidence.json',e);dump(a/'score.json',s)
 if trial.startswith('GUI'):log=gui[trial];start,end=log['start_ms'],log['end_ms'];logpath='pilot/gui_operation_log.json'
 else:
  log=read(folder/'live_mcp_log.json');start=log.get('start_ms',log.get('apply',{}).get('start_ms'));end=log.get('end_ms',log.get('apply',{}).get('end_ms'));logpath=f'pilot/{trial}/live_mcp_log.json'
 prompt=tasks[task];prompt_hash=hashlib.sha256(json.dumps(prompt,ensure_ascii=False).encode()).hexdigest()
 record={'trial_id':trial,'phase':'PILOT','task':task,'method':'codex_mcp' if trial.startswith('MCP') else 'codex_gui','status':'PASS' if s['strict_pass'] else 'FAIL','atoms_passed':sum(x['pass'] for x in s['atoms']),'atoms_total':len(s['atoms']),'strict_pass':s['strict_pass'],'operation_interval_s':round((end-start)/1000,3) if start is not None and end is not None else None,'start_ms':start,'end_ms':end,'timing_comparable':False,'timing_note':'Pilot operational diagnostic interval; MCP_T3 ends before GUI save, other MCP after saved-context read; GUI includes save; independent disk reopen/render separate. Not an end-to-end comparison.','prompt_sha256':prompt_hash,'actual_prompt':prompt,'baseline_sha256':sha(folder/'baseline/project.json'),'checks':s['checks'],'unexpected_paths':s['unexpected_paths'],'logs_path':logpath,'acceptance_path':str(a.relative_to(O)),'model_context':'shared current chat, not independent'}
 dump(folder/'pilot_record.json',record);results.append(record)
dump(P/'pilot_results.json',results)
with (P/'pilot_results.csv').open('w',encoding='utf-8-sig',newline='') as out:
 keys=['trial_id','phase','task','method','status','atoms_passed','atoms_total','operation_interval_s','timing_comparable','prompt_sha256','baseline_sha256','logs_path','acceptance_path'];w=csv.DictWriter(out,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(results)
# Negative controls derive from actual successful configurations, never user projects.
N=P/'negative_controls';N.mkdir(exist_ok=True)
r=next(v for v in results if v['trial_id']=='MCP_T3');a=P/'MCP_T3/acceptance';before=read(a/'before.json');good=read(a/'after.json');e=read(a/'evidence.json');checks=[]
for name,mutator,expected in [
 ('correct_real_sample',lambda f:None,True),
 ('wrong_target_color',lambda f:f['panels'][1]['series'][1].update(color='#E69F00'),False),
 ('unrelated_A_title',lambda f:f['panels'][0]['title_i18n'].update(zh='UNREQUESTED'),False),
 ('duplicate_panel',lambda f:f['panels'].append(copy.deepcopy(f['panels'][0])),False)]:
 final=copy.deepcopy(good);mutator(final);res=score(before,final,constraints['T3'],e,task_id='T3');dump(N/(name+'.json'),{'before':before,'after':final,'constraints':constraints['T3'],'evidence':e,'result':res});checks.append({'case':name,'expected':expected,'actual':res['strict_pass'],'passed':res['strict_pass']==expected})
for key in ['arrays','source_bytes','save_reopen','visual_review']:
 ev={**e,key:False};res=score(before,good,constraints['T3'],ev,task_id='T3');dump(N/(key+'_failure.json'),res);checks.append({'case':key+'_failure','expected':False,'actual':res['strict_pass'],'passed':not res['strict_pass']})
# Alter only a test-copy dataset; loader must reject its byte hash mismatch.
bad=N/'corrupt_project';shutil.copytree(P/'MCP_T3/saved',bad,dirs_exist_ok=True);doc=read(bad/'project.json');data=bad/doc['figure']['datasets'][0]['source_path'];data.chmod(0o600);raw=data.read_bytes();data.write_bytes(raw+b'\n')
try:
 w=Workbench(N/'corrupt_reader');w.open_project(bad/'project.json');rejected=False;message='unexpected load success'
except (ValueError,OSError) as exc:rejected=True;message=str(exc)
checks.append({'case':'real_corrupt_source_reopen','expected_rejection':True,'actual_rejection':rejected,'passed':rejected,'message':message});dump(N/'negative_control_results.json',checks)
# Export current turn's tool calls/results only. Never copy reasoning or credentials.
session=next(Path('C:/Users/A/.codex/sessions/2026/10/20').glob('*01a158f3-8fbb-7b13-8ef2-083769306a70*'));rows=[json.loads(x) for x in session.read_text(encoding='utf-8').splitlines()];startstamp='2026-10-20T00:00:00Z'
for rr in rows:
 q=rr.get('payload',{})
 if q.get('type')=='message' and q.get('role')=='user' and 'Stage 4 下一检查点' in str(q.get('content')):startstamp=rr['timestamp']
selected={}
for rr in rows:
 if rr.get('timestamp','')<startstamp:continue
 q=rr.get('payload',{})
 if (q.get('namespace')=='mcp__cua_repl' and q.get('type')=='function_call') or (q.get('type')=='custom_tool_call' and 'tools.mcp__wavelab__' in q.get('input','')):selected[q['call_id']]=rr
trace=[];screenshot_no=0
for rr in rows:
 q=rr.get('payload',{})
 if q.get('call_id') not in selected:continue
 entry={'timestamp':rr.get('timestamp'),'type':q.get('type'),'call_id':q.get('call_id')}
 if 'output' in q:
  content=[]
  for block in q['output'] if isinstance(q['output'],list) else [{'type':'text','text':q['output']}]:
   if block.get('type')=='input_image' and block.get('image_url','').startswith('data:'):
    url=block['image_url'];header,encoded=url.split(',',1);screenshot_no+=1;ext='jpg' if 'jpeg' in header else 'png';target=P/f'gui_screenshot_{screenshot_no:02d}.{ext}';target.write_bytes(base64.b64decode(encoded));content.append({'type':'image_file','path':target.name})
   else:content.append(block)
  entry['output']=content
 else:
  entry.update({k:q[k] for k in ['name','namespace','arguments','input'] if k in q})
 trace.append(entry)
with (P/'execution_trace.jsonl').open('w',encoding='utf-8') as stream:
 for row in trace:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
usage=[]
for rr in rows:
 if rr.get('type')!='token_usage_record' or rr.get('timestamp','')<startstamp:continue
 timestamp=datetime.datetime.fromisoformat(rr['timestamp'].replace('Z','+00:00')).timestamp()*1000
 for r in results:
  if r['start_ms'] is not None and r['start_ms']<=timestamp<=r['end_ms']:
   usage.append({'trial':r['trial_id'],'timestamp':rr['timestamp'],'usage':rr['payload']['usage']})
resource=[]
for r in results:
 records=[x['usage'] for x in usage if x['trial']==r['trial_id']];resource.append({'trial':r['trial_id'],'responses':len(records),'usage':{k:sum(v.get(k,0) for v in records) for k in ['input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens']}})
dump(P/'model_resource_records.json',{'boundary':'Responses timestamped within recorded diagnostic operation windows; excludes earlier planning and later acceptance; same long chat with cached context; not a forecast of independent fresh chats','per_trial':resource,'records':usage})
protected=read(O/'protected_manifest.json');changes=[p for p,h in protected.items() if not Path(p).exists() or sha(Path(p))!=h];dump(O/'protected_verification_pilot.json',{'checked_files':len(protected),'changed':changes,'pass':not changes})
print(json.dumps({'pilot_status':[(r['trial_id'],r['status'],r['operation_interval_s']) for r in results],'negative_controls':checks,'trace_records':len(trace),'screenshots':screenshot_no,'protection_changes':changes,'resource':resource},ensure_ascii=False))

"""Summarize observed formal v2 evidence; never supplies task actions or changes scoring."""
from pathlib import Path
import sys,json,csv,math,hashlib,statistics
R=Path(__file__).resolve().parents[1];O=R/'reports/stage_04';B=O/'formal_v2'
def read(p,default=None):return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default
def wilson(k,n):
 if not n:return [None,None]
 z=1.96;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;return [max(0,c-h),min(1,c+h)]
def aggregate():
 rows=[];schedule=read(B/'schedule.json')['schedule']+read(B/'supplemental_schedule.json',{'schedule':[]})['schedule'];constraints=read(O/'constraints.json')['tasks']
 for item in schedule:
  d=B/item['trial_id'];timing=read(d/'timing.json');release=read(d/'release.json')
  if not release or not timing:continue
  s=read(d/'acceptance/score.json',{});e=read(d/'acceptance/evidence.json',{});done=read(d/'execution_done.json',{});a=s.get('atoms',[])
  log_exception=read(d/'evidence/logging_exception.json',{});missing_logs=bool(log_exception.get('missing_raw_returns'))
  declared=done.get('status','').upper()
  finished=bool(timing) and timing.get('within_budget') is True and (declared in ['SUCCESS','PASS'] or declared.startswith('COMPLETED')) and not missing_logs
  strict=s.get('strict_pass') is True and finished
  errors=[]
  if not finished:errors.append('INCOMPLETE_RAW_LOG' if missing_logs else (timing or {}).get('status','MISSING_COMPLETION'))
  if not s:errors.append('MISSING_ACCEPTANCE')
  errors += ['atom:'+x['id'] for x in a if not x['pass']]
  errors += ['check:'+k for k,v in s.get('checks',{}).items() if not v]
  row={'trial_id':d.name,'phase':'FORMAL_V2','cohort':'direct_tools_v2','order':item['order'],'task':item['task'],'method':'codex_'+item['method'].lower(),'status':'PASS' if strict else ('TIMEOUT' if (timing or {}).get('status')=='TIMEOUT' or not (timing or {}).get('within_budget',False) else 'FAIL'),'strict_pass':strict,'atoms_passed':sum(x['pass'] for x in a),'atoms_total':len(a) or len(constraints[item['task']]),'atoms_assessed':len(a),'atoms_unmeasured':0 if a else len(constraints[item['task']]),'atomic_rate':s.get('atomic_rate','NOT_MEASURED'),'task_s':(timing or {}).get('task_s','NOT_COMPLETED'),'time_censored_s':(timing or {}).get('censored_s',300),'timing_comparable':True,'non_target_changes':len(s.get('unexpected_paths',[])) if s else 'NOT_MEASURED','data_consistency':e.get('arrays') is True and e.get('source_bytes') is True if e else 'NOT_MEASURED','save_reopen':False if done.get('saved') is False or done.get('reopened') is False else e.get('save_reopen','NOT_MEASURED'),'rejection_ok':e.get('rejection_observed','NOT_APPLICABLE'),'recovery_ok':e.get('recovery_success','NOT_APPLICABLE'),'failure_reason':';'.join(errors),'logs_path':str(d.relative_to(O)/'evidence'),'acceptance_path':str(d.relative_to(O)/'acceptance'),'model_tokens':'NOT_MEASURED','model_cost':'NOT_MEASURED'};rows.append(row)
 for row in rows:
  d=B/row['trial_id'];row['quality_acceptance_pass']=read(d/'acceptance/score.json',{}).get('strict_pass','NOT_MEASURED');row['agent_status']=read(d/'execution_done.json',{}).get('status','MISSING');row['missing_raw_returns']=len(read(d/'evidence/logging_exception.json',{}).get('missing_raw_returns',[]))
  guard=read(d/'evidence/guard_snapshot.json',{});row['gui_guard_events_recorded']=len(guard.get('events',[])) if isinstance(guard,dict) else 'NOT_MEASURED';row['resource_interruption']=(d/'evidence/resource_interruption.json').exists()
  row['orchestration_delay']=(d/'evidence/orchestration_delay.json').exists()
  if read(d/'execution_done.json',{}).get('reopen_verified') is False:row['save_reopen']=False
  if row['resource_interruption'] or row['orchestration_delay']:row['timing_comparable']=False
  if row['status']=='TIMEOUT':row['bookkeeping_end_s']=row['task_s'];row['task_s']='NOT_COMPLETED'
  if row['order']>24:row.update(phase='FORMAL_SUPPLEMENTAL',cohort='supplemental_user_requested')
 legacy=list(csv.DictReader((O/'history/pre_v2_raw_results.csv').open(encoding='utf-8-sig',newline='')))
 allrows=legacy+rows;fields=list(dict.fromkeys(k for row in allrows for k in row))
 for path,contents in [(O/'raw_results.csv',allrows),(B/'raw_results.csv',rows)]:
  with path.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fields);w.writeheader();w.writerows(contents)
 supplemental=[x for x in rows if x['order']>24];rows=[x for x in rows if x['order']<=24];summaries=[]
 for task in ['T1','T2','T3','T4']:
  for method in ['codex_mcp','codex_gui']:
   subset=[x for x in rows if x['task']==task and x['method']==method];n=len(subset);k=sum(x['strict_pass'] for x in subset);times=[x['time_censored_s'] for x in subset if isinstance(x['time_censored_s'],(int,float))];ap=sum(x['atoms_passed'] for x in subset);at=sum(x['atoms_total'] for x in subset)
   assessed=sum(x['atoms_assessed'] for x in subset)
   summaries.append({'task':task,'method':method,'started_n':n,'strict_passes':k,'strict_rate':k/n if n else None,'wilson95':wilson(k,n),'atoms_passed':ap,'atoms_total':at,'atoms_assessed':assessed,'atoms_unmeasured':at-assessed,'atomic_rate':ap/assessed if assessed else None,'requested_constraint_lower_bound':ap/at if at else None,'observed_time_s':times,'median_observed_s':statistics.median(times) if times else None,'timeouts':sum(x['status']=='TIMEOUT' for x in subset)})
 out={'planned':24,'observed':len(rows),'legacy_observations':len(legacy),'supplemental_observations':len(supplemental),'supplemental_rows':supplemental,'pilot_included':False,'summaries':summaries,'rows':rows};(B/'statistics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'observed':len(rows),'strict_passes':sum(x['strict_pass'] for x in rows),'supplemental_observations':len(supplemental)},ensure_ascii=False))
 return out
def plots(data):
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 import numpy as np
 plt.rcParams['font.sans-serif']=['Microsoft YaHei','SimSun'];plt.rcParams['axes.unicode_minus']=False
 out=B/'figures';out.mkdir(exist_ok=True);s=data['summaries'];colors=['#0072B2','#D55E00']
 for field,label,name in [('strict_rate','严格完成率（95% Wilson区间）','strict_completion')]:
  fig,ax=plt.subplots(figsize=(7,4));x=np.arange(4)
  for j,m in enumerate(['codex_mcp','codex_gui']):
   group=[next(z for z in s if z['task']==t and z['method']==m) for t in ['T1','T2','T3','T4']];vals=[z[field] if z[field] is not None else 0 for z in group];err=[[v-(z['wilson95'][0] or 0) for v,z in zip(vals,group)],[(z['wilson95'][1] or 0)-v for v,z in zip(vals,group)]];ax.bar(x+(j-.5)*.34,vals,.34,label=m,color=colors[j],yerr=err,capsize=3)
  ax.set(xticks=x,xticklabels=['T1','T2','T3','T4'],ylim=(0,1.15),ylabel=label);ax.legend(frameon=False);fig.tight_layout();fig.savefig(out/(name+'.png'),dpi=220);fig.savefig(out/(name+'.pdf'));plt.close(fig)
 fig,ax=plt.subplots(figsize=(8,4));x=np.arange(4)
 for j,m in enumerate(['codex_mcp','codex_gui']):
  g=[next(z for z in s if z['task']==t and z['method']==m) for t in ['T1','T2','T3','T4']];pos=x+(j-.5)*.34
  good=[z['atoms_passed']/z['atoms_total'] if z['atoms_total'] else 0 for z in g];bad=[(z['atoms_assessed']-z['atoms_passed'])/z['atoms_total'] if z['atoms_total'] else 0 for z in g];unknown=[z['atoms_unmeasured']/z['atoms_total'] if z['atoms_total'] else 0 for z in g]
  ax.bar(pos,good,.34,color=colors[j],label=m);ax.bar(pos,bad,.34,bottom=good,color='#B22222',label='已测不满足' if j==0 else None);ax.bar(pos,unknown,.34,bottom=np.array(good)+np.array(bad),color='0.78',hatch='//',label='未测量' if j==0 else None)
  for xx,z in zip(pos,g):ax.text(xx,1.02,f"{z['atoms_passed']}/{z['atoms_total']}",ha='center',fontsize=8)
 ax.set(xticks=x,xticklabels=['T1','T2','T3','T4'],ylim=(0,1.18),ylabel='全部要求中确认满足的原子约束比例');ax.legend(frameon=False,fontsize=8,loc='lower left');fig.tight_layout();fig.savefig(out/'atomic_satisfaction.png',dpi=220);fig.savefig(out/'atomic_satisfaction.pdf');plt.close(fig)
 fig,ax=plt.subplots(figsize=(8,4))
 for row in data['rows']:
  i=['T1','T2','T3','T4'].index(row['task']);j=0 if row['method']=='codex_mcp' else 1;ax.scatter(i+(j-.5)*.25+(int(row['trial_id'].split('_')[2][1:])-2)*.035,row['time_censored_s'],c=colors[j],marker='^' if row['status']=='TIMEOUT' else ('o' if row['strict_pass'] else 'x'),s=55)
 from matplotlib.lines import Line2D
 ax.axhline(300,color='0.6',linestyle='--',linewidth=.8);ax.set(xticks=range(4),xticklabels=['T1','T2','T3','T4'],ylabel='操作耗时 / s（超时右删失于300秒）');ax.legend(handles=[Line2D([],[],color=colors[0],marker='o',linestyle='',label='Codex + MCP'),Line2D([],[],color=colors[1],marker='o',linestyle='',label='Codex + GUI'),Line2D([],[],color='0.3',marker='^',linestyle='',label='超时（右删失）'),Line2D([],[],color='0.3',marker='x',linestyle='',label='验收/证据未达标')],frameon=False,fontsize=8);fig.tight_layout();fig.savefig(out/'all_trial_times.png',dpi=220);fig.savefig(out/'all_trial_times.pdf');plt.close(fig)
if __name__=='__main__':
 data=aggregate()
 if '--plots' in sys.argv:plots(data)

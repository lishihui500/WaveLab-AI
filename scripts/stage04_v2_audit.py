"""Read-only final integrity/evidence audit. Writes experiment evidence only."""
from pathlib import Path
import json,hashlib,collections
R=Path(__file__).resolve().parents[1];O=R/'reports/stage_04';B=O/'formal_v2'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
freeze=read(B/'freeze.json')['files'];protected=read(O/'protected_manifest.json');supp=read(B/'supplemental_freeze.json')['files']
schedule=read(B/'schedule.json')['schedule']+read(B/'supplemental_schedule.json')['schedule'];prompts=read(O/'tasks.json')['prompts'];rows=[]
for item in schedule:
 d=B/item['trial_id'];t=read(d/'task_input.json') if (d/'task_input.json').exists() else None
 g=read(d/'evidence/guard_snapshot.json') if (d/'evidence/guard_snapshot.json').exists() else {}
 row={'trial_id':d.name,'baseline_sha256':sha(d/'baseline/project.json'),'released':t is not None,'recorded_task_input_matches_frozen':t['full_task']==prompts[item['task']] if t else None,'saved_project_exists':(d/'saved/project.json').exists(),'guard_events':len(g.get('events',[])),'guard_binding_evidence':'PRESENT_NOT_GLOBAL_INTERCEPTOR' if g.get('events') else 'NOT_VERIFIED','resource_interruption':(d/'evidence/resource_interruption.json').exists(),'orchestration_delay':(d/'evidence/orchestration_delay.json').exists(),'acceptance_error_retained':(d/'acceptance/acceptance_error.json').exists()}
 if (d/'evidence/logging_exception.json').exists():row['missing_raw_returns']=read(d/'evidence/logging_exception.json').get('missing_raw_returns',[])
 if (d/'acceptance/score.json').exists():
  a=d/'acceptance';e=read(a/'evidence.json');c=read(O/'constraints.json')['tasks'][item['task']]
  packet={'before':read(a/'before.json'),'after':read(a/'canonical_after.json'),'constraints':c,'evidence':e,'task_id':item['task']}
  (a/'scoring_packet.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2),encoding='utf-8')
 rows.append(row)
report={'frozen_input_count':len(freeze),'frozen_input_changes':[p for p,h in freeze.items() if not (R/p).is_file() or sha(R/p)!=h],'protected_count':len(protected),'protected_changes':[p for p,h in protected.items() if not (R/p).is_file() or sha(R/p)!=h],'supplemental_frozen_changes':[p for p,h in supp.items() if not (R/p).is_file() or sha(R/p)!=h],'baseline_hash_counts':dict(collections.Counter(r['baseline_sha256'] for r in rows)),'rows':rows,'note':'missing/empty guard events indicate evidence limitation; positive counts alone do not prove global interception or every call coverage. Unavailable raw results are not reconstructed from final state.'}
(B/'final_integrity_and_evidence_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ['rows','note']},ensure_ascii=False))
if report['frozen_input_changes'] or report['protected_changes'] or report['supplemental_frozen_changes']:raise SystemExit(1)

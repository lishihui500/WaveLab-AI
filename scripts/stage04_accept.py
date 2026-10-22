"""Read-only Pilot acceptance; writes only Stage 4 artifacts. No task execution."""
from pathlib import Path
import argparse,sys,json,hashlib,time,copy
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'scripts'))
from wavelab.workbench import Workbench
from wavelab.render.engine import render_figure,export_figure
from stage04_score import score
from stage03f_validate import geometry_checks

def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def norm(w):
 d=w.spec.model_dump(mode='json')
 for x in d['datasets']: x['source_path']=Path(x['source_path']).name
 return d

def accept(root):
 root=Path(root).resolve();out=root/'acceptance';out.mkdir(exist_ok=True)
 before=Workbench(out/'reader_before');before.open_project(root/'baseline/project.json')
 final=Workbench(out/'reader_final');final.open_project(root/'saved/project.json')
 b,a=norm(before),norm(final);e={}
 e['arrays']=before.datasets.keys()==final.datasets.keys() and all(np.array_equal(x.samples,final.datasets[k].samples) and np.array_equal(x.time_s,final.datasets[k].time_s) for k,x in before.datasets.items())
 e['source_bytes']=all(digest(x.manifest.source_path)==digest(final.datasets[k].manifest.source_path) for k,x in before.datasets.items())
 e['identity']=b['datasets']==a['datasets']
 fresh=Workbench(out/'fresh_reader');fresh.open_project(root/'saved/project.json');e['save_reopen']=norm(fresh)==a and all(np.array_equal(x.samples,fresh.datasets[k].samples) for k,x in final.datasets.items())
 r=render_figure(fresh.spec,fresh.datasets);g=geometry_checks(r,fresh.spec,'zh');e['render_geometry']=all(t['inside_figure'] for t in g['texts']) and all(z['inside_parent'] and z['bounds_match'] for z in g['insets'])
 for ext in ['png','pdf']: export_figure(r,out/f'final.{ext}')
 r.figure.clear();e['visual_review']=False
 task=root.name.split('_')[1]
 if task=='T4':
  if (root/'live_mcp_log.json').exists():
   log=json.loads((root/'live_mcp_log.json').read_text(encoding='utf-8'));initial=json.loads(log['before']['content'][0]['text']);mid=json.loads(log['intermediate']['content'][0]['text']);reject=json.loads(log['rejected']['result']['content'][0]['text']);recover=json.loads(log['recovery']['result']['content'][0]['text'])
   e['rejection_observed']=reject.get('error')=='validation_error'
   e['rejected_state_unchanged']=initial['context']==mid['context'] and initial['revision']==mid['revision'] and initial['fingerprint']==mid['fingerprint']
   e['recovery_success']=recover.get('result',{}).get('status')=='applied' and a['time_axis']['xlim']==[1.4,1.6]
  elif (root/'rejected_project.json').exists():
   from wavelab.domain.figure import FigureSpec
   mid=FigureSpec.model_validate(json.loads((root/'rejected_project.json').read_text(encoding='utf-8'))['figure']).model_dump(mode='json')
   for x in mid['datasets']: x['source_path']=Path(x['source_path']).name
   log=next(v for v in json.loads((root.parent/'gui_operation_log.json').read_text(encoding='utf-8')) if v['trial']==root.name)
   e['rejection_observed']='strictly increasing' in log.get('rejection_snapshot','')
   e['rejected_state_unchanged']=mid==b
   e['recovery_success']=a['time_axis']['xlim']==[1.4,1.6]
 constraints=json.loads((ROOT/'reports/stage_04/constraints.json').read_text(encoding='utf-8'))['tasks'][task]
 canonical=copy.deepcopy(a)
 if task=='T2':
  ids=[z['id'] for panel in a['panels'] for z in panel['insets']]
  e['inset_ids_unique']=len(ids)==3 and len(set(ids))==3 and all(ids)
  for i,panel in enumerate(canonical['panels']):
   for z in panel['insets']: z['id']=f'stage4_inset_{i}'
 (out/'canonical_after.json').write_text(json.dumps(canonical,ensure_ascii=False,indent=2),encoding='utf-8')
 result=score(b,canonical,constraints,e,task_id=task)
 for n,v in [('before.json',b),('after.json',a),('geometry.json',g),('evidence.json',e),('score.json',result)]: (out/n).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'trial':root.name,'atoms':f"{sum(x['pass'] for x in result['atoms'])}/{len(result['atoms'])}",'checks':result['checks'],'unexpected':result['unexpected_paths']},ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('root');args=p.parse_args();accept(args.root)

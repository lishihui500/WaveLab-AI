"""Read-only checks for neutral infrastructure roundtrips, NOT formal scoring."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from wavelab.workbench import Workbench

def verify(mode):
 root=R/'reports/stage_04/infrastructure_v2/probes'/mode
 a=Workbench(root/'readers/initial');a.open_project(root/'baseline/project.json')
 b=Workbench(root/'readers/reopened');b.open_project(root/'saved/project.json')
 def norm(w):
  d=w.spec.model_dump(mode='json')
  for ds in d['datasets']:ds['source_path']=Path(ds['source_path']).name
  return d
 x,y=norm(a),norm(b);expected=json.loads(json.dumps(x));expected['panels'][0]['title_i18n']['zh']='基础设施通道检查'
 checks={'only_requested_title_changed':expected==y,'persistent_ids_preserved':[p.id for p in a.spec.panels]==[p.id for p in b.spec.panels], 'arrays_exact':a.datasets.keys()==b.datasets.keys() and all(np.array_equal(d.samples,b.datasets[k].samples) and np.array_equal(d.time_s,b.datasets[k].time_s) for k,d in a.datasets.items()),'source_bytes_exact':all(Path(d.manifest.source_path).read_bytes()==Path(b.datasets[k].manifest.source_path).read_bytes() for k,d in a.datasets.items())}
 report={'scope':'Infrastructure neutral operation, not formal experiment','mode':mode,'checks':checks,'pass':all(checks.values()),'saved_project_sha256':hashlib.sha256((root/'saved/project.json').read_bytes()).hexdigest()};(root/'independent_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':verify(sys.argv[1])

"""Read-only audits of old freeze and protected files; writes only v2 evidence."""
from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[1];D=R/'reports/stage_04'
def changed(manifest):
 return [p for p,h in manifest.items() if not (R/p).is_file() or hashlib.sha256((R/p).read_bytes()).hexdigest()!=h]
freeze=json.loads((D/'formal_freeze.json').read_text(encoding='utf-8'))['files']
protected=json.loads((D/'protected_manifest.json').read_text(encoding='utf-8'))
raw=hashlib.sha256((D/'raw_results.csv').read_bytes()).hexdigest()
result={'old_frozen_count':len(freeze),'old_frozen_changed':changed(freeze),'protected_count':len(protected),'protected_changed':changed(protected),'old_formal_raw_results_sha256':raw,'old_formal_raw_results_unchanged':raw=='1a0911b9f7335b7d6ba849fcac8cf0730416bbe392df38a469ae6e2cd9e976fa'}
(D/'infrastructure_v2/integrity_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if result['old_frozen_changed'] or result['protected_changed'] or not result['old_formal_raw_results_unchanged']:raise SystemExit(1)

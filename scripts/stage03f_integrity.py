"""Read-only source and immutable-baseline guard; exits nonzero on any change."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/stage_03F'
def main():
    changed=[];count=0
    records=json.loads((OUT/'protected_before.json').read_text(encoding='utf-8'))
    for row in records:
        p=ROOT/row['path'];count+=1
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:changed.append(str(p))
    for row in json.loads((OUT/'initial_manifest.json').read_text(encoding='utf-8')):
        for f in row['files']:
            p=OUT/'baselines'/row['task']/f['path'];count+=1
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=f['sha256']:changed.append(str(p))
    result=dict(checked_files=count,changed=changed,passed=not changed)
    (OUT/'source_integrity.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True));raise SystemExit(bool(changed))
if __name__=='__main__':main()

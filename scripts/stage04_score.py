"""Stage 4 independent exact-constraint scorer. Never executes plotting actions."""
import argparse, copy, hashlib, json
from pathlib import Path

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def leaves(value, prefix=''):
    if isinstance(value, dict):
        result={}
        for key, item in value.items(): result.update(leaves(item, prefix+'/'+str(key)))
        return result or {prefix: value}
    if isinstance(value, list):
        result={prefix+'/@length':len(value)}
        for index,item in enumerate(value): result.update(leaves(item,prefix+'/'+str(index)))
        return result
    return {prefix:value}

def score(before, after, constraints, evidence, task_id=None):
    """Paths refer to complete FigureSpec; absent evidence cannot pass."""
    old,new=leaves(before),leaves(after)
    atoms=[]
    allowed={c['path'] for c in constraints}
    for c in constraints:
        p=c['path']; passed=p in new and type(new[p]) is type(c['equals']) and new[p]==c['equals']
        atoms.append({'id':c['id'],'path':p,'expected':c['equals'],'actual':new.get(p),'pass':passed})
    changed=[p for p in old.keys()|new.keys() if (p in old)!=(p in new) or old.get(p)!=new.get(p)]
    unexpected=sorted(p for p in changed if p not in allowed and not (p in old and p not in new and any(q.startswith(p+'/') for q in allowed)))
    required=['source_bytes','arrays','identity','save_reopen','render_geometry','visual_review']
    if task_id=='T2': required += ['inset_ids_unique']
    if task_id=='T4': required += ['rejection_observed','rejected_state_unchanged','recovery_success']
    checks={k:evidence.get(k) is True for k in required}
    checks['non_target_unchanged']=not unexpected
    return {'atoms':atoms,'atomic_rate':sum(a['pass'] for a in atoms)/len(atoms) if atoms else None,
            'checks':checks,'unexpected_paths':unexpected,
            'strict_pass':bool(atoms) and all(a['pass'] for a in atoms) and all(checks.values())}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('packet',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    packet=json.loads(a.packet.read_text(encoding='utf-8'))
    a.output.write_text(json.dumps(score(**packet),ensure_ascii=False,indent=2),encoding='utf-8')

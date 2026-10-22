"""Deterministic fixture preparation ONLY; never executes measured drawing tasks."""
from pathlib import Path
import copy, hashlib, json, shutil, sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from wavelab.domain.figure import FigureSpec

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/stage_03F'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    if (OUT/'initial_manifest.json').exists():
        raise SystemExit('Fixtures already exist; refusing to reset experiments')
    protected=[]
    for base in [ROOT/'reports/stage_03E',ROOT/'.wavelab/projects',ROOT/'.wavelab/imports',ROOT/'test/fixtures']:
        if base.exists():
            protected += [dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in base.rglob('*') if p.is_file()]
    protected += [dict(path=str(p.relative_to(ROOT)),sha256=sha(p)) for p in ROOT.glob('*.txt')]
    write(OUT/'protected_before.json',protected)
    source=ROOT/'reports/stage_03E/initial/six_single'
    doc=json.loads((source/'project.json').read_text(encoding='utf-8'))
    palette=['#0072B2','#D55E00','#009E73','#CC79A7','#E69F00','#56B4E9']
    for s,color in zip(doc['figure']['panels'][0]['series'],palette): s['color']=color
    rows=[]
    for task in ['F01','F02','F03']:
        value=copy.deepcopy(doc)
        if task!='F01':
            seed=value['figure']['panels'][0]
            value['figure']['panels']=[]
            for i,phase in enumerate('ABC'):
                panel=copy.deepcopy(seed);panel['id']='f_seed_'+phase.lower()
                panel['series']=copy.deepcopy(seed['series'][2*i:2*i+2]);panel['insets']=[]
                value['figure']['panels'].append(panel)
        FigureSpec.model_validate(value['figure'])
        base=OUT/'baselines'/task
        shutil.copytree(source/'data',base/'data')
        write(base/'project.json',value)
        paths=[]
        for mode in ['mcp','gui']:
            for repeat in range(1,4):
                dest=OUT/'runs'/mode/f'{task}_R{repeat}'
                shutil.copytree(base,dest);paths.append(str((dest/'project.json').relative_to(ROOT)))
        manual=OUT/'manual'/f'{task}_manual_start';shutil.copytree(base,manual)
        files=[dict(path=str(p.relative_to(base)),sha256=sha(p)) for p in base.rglob('*') if p.is_file()]
        rows.append(dict(task=task,baseline=str((base/'project.json').relative_to(ROOT)),manual=str((manual/'project.json').relative_to(ROOT)),runs=paths,figure=value['figure'],files=files,mapping='Synthetic fixture explicitly assigns columns 1..6 to A upper,A lower,B upper,B lower,C upper,C lower; original headers remain repeated Ucap.',data_origin='3E synthetic six_single; all six series receive explicit baseline colors to make preservation testable'))
        for p in base.rglob('*'):
            if p.is_file():p.chmod(0o444)
    write(OUT/'initial_manifest.json',rows)
    print(json.dumps([dict(task=r['task'],baseline=r['baseline'],runs=r['runs']) for r in rows],indent=2))
if __name__=='__main__':main()

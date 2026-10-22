"""Post-experiment verification and image grouping; never executes benchmark actions."""
from pathlib import Path
import hashlib, importlib.util, json
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/stage_03F'
module=importlib.util.spec_from_file_location('acceptance',ROOT/'scripts/stage03f_validate.py')
acceptance=importlib.util.module_from_spec(module);module.loader.exec_module(acceptance)

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    results=[]
    for mode in ['MCP','GUI']:
        for task in ['F01','F02','F03']:
            repeats=range(1,5) if mode=='GUI' and task=='F01' else range(1,4)
            for repeat in repeats:
                identity=f'{mode}_{task}_R{repeat}'
                path=ROOT/'.wavelab/projects'/f'Stage03F_{identity}'/'project.json'
                if not path.exists():
                    results.append(dict(trial=identity,error='Saved project missing'));continue
                target=OUT/'artifacts'/f'{mode.lower()}_{task}_R{repeat}'
                result=acceptance.validate(task,path,target)
                results.append(dict(trial=identity,passed=result['passed'],failed_checks=[k for k,v in result['checks'].items() if not v],acceptance=str((target/'acceptance.json').relative_to(OUT))))
                print(identity,result['passed'],flush=True)
    dump(OUT/'final_acceptance_index.json',results)
    groups={}
    for folder in sorted((OUT/'artifacts').iterdir()):
        if not folder.is_dir():continue
        for path in sorted(folder.glob('final_*.png')):
            with Image.open(path) as original:
                im=original.convert('RGB');key=hashlib.sha256(str(im.size).encode()+im.tobytes()).hexdigest()
                groups.setdefault(key,dict(pixel_sha256=key,size=list(im.size),representative=str(path.relative_to(OUT)),members=[]))['members'].append(str(path.relative_to(OUT)))
    review=OUT/'review_sheets';review.mkdir(exist_ok=True)
    groups=list(groups.values())
    for i,g in enumerate(groups):g['group_id']=f'G{i+1:02d}'
    for start in range(0,len(groups),4):
        batch=groups[start:start+4];sheet=Image.new('RGB',(1600,1420),'#edf0f4');draw=ImageDraw.Draw(sheet)
        for j,g in enumerate(batch):
            image=Image.open(OUT/g['representative']).convert('RGB');image.thumbnail((780,660))
            x=(j%2)*800+10;y=(j//2)*710+35
            draw.text((x,y-25),g['group_id']+' '+g['representative'],fill='black')
            sheet.paste(image,(x,y))
            g['review_sheet']=str((review/f'sheet_{start//4+1:02d}.png').relative_to(OUT))
        sheet.save(review/f'sheet_{start//4+1:02d}.png')
    dump(OUT/'image_equivalence_groups.json',groups)
    product=json.loads((OUT/'environment.json').read_text(encoding='utf-8-sig'))
    checks=[]
    for row in product['source_hashes']:
        path=Path(row['path']);actual=hashlib.sha256(path.read_bytes()).hexdigest()
        checks.append(dict(path=row['path'],unchanged=actual.lower()==row['sha256'].lower()))
    dump(OUT/'product_source_integrity.json',dict(all_unchanged=all(r['unchanged'] for r in checks),files=checks))
    print('Saved',len(results),'trial checks and',len(groups),'unique image groups',flush=True)

if __name__=='__main__':main()

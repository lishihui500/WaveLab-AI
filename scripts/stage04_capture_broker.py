"""Capture raw root browser tool observation for a literal broker request."""
from pathlib import Path
import json,sys,base64
trial,req=sys.argv[1:3];out=Path('reports/stage_04/formal')/trial/'broker';out.mkdir(exist_ok=True)
p=next(Path('C:/Users/A/.codex/sessions/2026/10/20').glob('*01a158f3-8fbb-7b13-8ef2-083769306a70*'))
rows=[json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()];call=next(r for r in reversed(rows) if r.get('payload',{}).get('namespace')=='mcp__cua_repl' and r['payload'].get('type')=='function_call');q=call['payload'];result=next(r for r in reversed(rows) if r.get('payload',{}).get('type')=='function_call_output' and r['payload'].get('call_id')==q['call_id']);blocks=[]
for i,b in enumerate(result['payload']['output']):
 if b.get('type')=='input_image' and b.get('image_url','').startswith('data:'):
  header,value=b['image_url'].split(',',1);ext='jpg' if 'jpeg' in header else 'png';image=out/f'{req}_{i}.{ext}';image.write_bytes(base64.b64decode(value));blocks.append({'type':'image_file','path':str(image.resolve())})
 else:blocks.append(b)
v={'id':req,'tool':'cua','arguments':json.loads(q['arguments']),'start_utc':call['timestamp'],'end_utc':result['timestamp'],'result':blocks};target=out/f'cua_{req}.json';target.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8');print(target.resolve())

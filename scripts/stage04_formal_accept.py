"""Formal acceptance wrapper; same scoring requirements as validated Pilot."""
from pathlib import Path
import sys,json,traceback
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from stage04_accept import accept
root=Path(sys.argv[1]);
try:accept(root)
except Exception as exc:
 out=root/'acceptance';out.mkdir(exist_ok=True);(out/'acceptance_error.json').write_text(json.dumps({'error':type(exc).__name__,'message':str(exc),'strict_pass':False,'traceback':traceback.format_exc()},ensure_ascii=False,indent=2),encoding='utf-8');print('ACCEPTANCE_FAILED',str(exc))

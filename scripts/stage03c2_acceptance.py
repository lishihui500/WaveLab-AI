"""Local synthetic comparison and six-series regression evidence; no model calls."""
from pathlib import Path
import json
import numpy as np
from wavelab.workbench import Workbench
from wavelab.ai.manual import ManualExchange, protocol
from wavelab.ai.assistant import figure_context

root=Path('reports/stage_03C2').resolve();root.mkdir(parents=True,exist_ok=True)
w=Workbench(root/'workspace')
did=w.import_bytes(b'Domain,Ucap1,Ucap2,Ucap3,Ucap4,Ucap5,Ucap6\n0,1,2,3,4,5,6\n1,2,3,4,5,6,7\n2,1,2,3,4,5,6','synthetic.txt')
w.assign_channels('panel_1',[c.channel_id for c in w.spec.datasets[0].channels])
w.import_bytes(b'Domain,unused1,unused2\n0,1,2\n1,2,3','unrelated.txt')
e=ManualExchange();s=e.generate(w,'将曲线的图例名字，与其对应通道的名称改成一致的')
new=json.loads(s.prompt.split('\n\n')[-1]);old=dict(new,figure_context=figure_context(w),protocol=protocol())
legacy=s.prompt.split('\n\n')[0]+'\n\n'+s.prompt.split('\n\n')[1]+'\n\n'+json.dumps(old,ensure_ascii=False,indent=2)
(root/'request_before.txt').write_text(legacy,encoding='utf-8');(root/'request_after.txt').write_text(s.prompt,encoding='utf-8')
comparison={key:{'characters':len(text),'lines':len(text.splitlines()),'channels':sum(len(d['channels']) for d in doc['figure_context']['datasets']),'response_schema_copies':int('response_schema' in doc['protocol'])+1} for key,text,doc in [('before_reconstructed_3C1',legacy,old),('after_3C2',s.prompt,new)]}
assert comparison['after_3C2']['lines']<200
(root/'request_comparison.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2),encoding='utf-8')
actions=[dict(action='update_series',panel_id='panel_1',channel_id=c.channel_id,changes={'label_i18n':dict(zh=c.display_name,en=c.display_name)}) for c in w.spec.datasets[0].channels]
raw=json.dumps(dict(new['binding'],plan=dict(summary='六条图例同步通道名称',actions=actions)),ensure_ascii=False)
(root/'scripted_response.json').write_text(raw,encoding='utf-8')
samples=w.datasets[did].samples.copy()
w.update(['panels',0,'ylabel_i18n','en'],'Capacitor voltage (kV)');manual=w.spec
p=e.validate(w,raw,source='scripted_json');assert e.merge_state=='merged';(root/'merged_preview.png').write_bytes(p.preview)
e.apply(w);applied=w.spec
w.undo();assert w.spec==manual
w.redo();assert w.spec==applied
saved=w.save_project('six_legend_merge');other=Workbench(root/'restored');other.open_project(saved)
assert other.spec.panels==w.spec.panels
np.testing.assert_array_equal(other.datasets[did].samples,samples)
(root/'acceptance.json').write_text(json.dumps(dict(source='scripted_json',model_calls=0,merge_state=e.merge_state,manual_fields=e.manual_changes,ai_fields=e.ai_changes,undo_preserves_manual=True,save_reopen=True,samples_unchanged=True),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(comparison,ensure_ascii=False,indent=2))

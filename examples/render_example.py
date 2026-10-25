"""Deterministic synthetic demonstration, without any LLM/API calls."""
from pathlib import Path
import hashlib
from wavelab.workbench import Workbench
from wavelab.commands import Plan, prepare, apply_proposal

ROOT=Path(__file__).resolve().parents[1]

def main():
    source=ROOT/'examples/synthetic_six_arms.csv'
    raw=source.read_bytes();before=hashlib.sha256(raw).hexdigest()
    w=Workbench(ROOT/'.wavelab')
    identity=w.import_bytes(raw,source.name)
    w.map_channels(identity,'Ucap','six_arms','公开合成示例定义：源列1至6依次为A上/A下/B上/B下/C上/C下，单位kV',unit='kV')
    actions=[dict(action='set_channel_properties',channel_id=f'{identity}:col_{i+1}',
                  evidence_quote='源单位 kV', changes={'quantity_name':'voltage','unit':'kV'})
             for i in range(6)]
    for phase_index,phase in enumerate('ABC'):
        pid='panel_1' if phase_index==0 else 'demo_'+phase.lower()
        if phase_index:actions.append(dict(action='create_panel',panel_id=pid))
        for j in range(2):
            i=phase_index*2+j+1
            actions.append(dict(action='add_series',panel_id=pid,channel_id=f'{identity}:col_{i}',changes=dict(color=['#0072B2','#D55E00'][j],linestyle=['-','--'][j],linewidth_pt=1.2,visible=True)))
        actions.append(dict(action='update_panel',panel_id=pid,changes={'title_i18n':{'zh':phase+'相','en':'Phase '+phase},'scientific_y':'never'}))
        actions.append(dict(action='create_inset',panel_id=pid,inset_id='demo_zoom_'+phase.lower(),changes={'xlim_s':[1.40,1.44],'bounds':[0.56,0.52,0.4,0.4]}))
    actions.append(dict(action='set_page',changes={'preset':'ieee_double_column'}))
    apply_proposal(w,prepare(w,Plan(summary='固定脚本复现合成六桥臂绘图；未调用模型',actions=actions), request='公开合成六桥臂电压示例，源单位 kV'))
    project=w.save_project('Synthetic_six_arms')
    paths,_=w.export('synthetic_six_arms',formats=('pdf','png'),bilingual=False)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    assert next(iter(w.data.values())).samples.shape==(601,7)
    print('Imported package:',__import__('wavelab').__file__)
    print('Saved project:',project)
    for p in paths:print('Exported:',p)
    print('PASS: 601 samples x 6 channels; original source hash unchanged. No AI calls.')

if __name__=='__main__':main()

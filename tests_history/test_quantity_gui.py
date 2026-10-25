from pathlib import Path
from streamlit.testing.v1 import AppTest
from wavelab.workbench import Workbench
from wavelab.channel_properties_ui import apply_channel_table
ROOT=Path(__file__).resolve().parents[1]
def element(at,kind,label):return next(e for e in getattr(at,kind) if e.label==label)
def loaded(tmp_path):
    w=Workbench(tmp_path);w.import_bytes(b'Domain,u\n0,25000\n0.1,26000\n0.2,24000','sample.txt')
    w.assign_channels('panel_1',[w.spec.datasets[0].channels[0].channel_id])
    at=AppTest.from_file(ROOT/'app.py',default_timeout=45);at.session_state['workbench']=w;at.run()
    assert not at.exception
    return at,w

def test_gui_table_transaction_and_style_undo(tmp_path):
    at,w=loaded(tmp_path);m=w.spec.datasets[0];c=m.channels[0]
    apply_channel_table(w,m,dict(binding=w.project_epoch,revision=w.revision,rows=[dict(channel_id=c.channel_id,display_name='通道名',quantity_name='voltage',unit='V')]))
    at.run();assert not at.exception
    element(at,'text_input','颜色（留空使用科研配色）').input('red').run()
    element(at,'button','撤销').click().run()
    assert w.spec.datasets[0].channels[0].display_name=='通道名'
    assert w.spec.panels[0].series[0].color is None
    assert not any(e.label in ('Y轴分类','Y轴物理量预设') for e in at.selectbox)

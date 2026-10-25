import json
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from wavelab.workbench import Workbench
from wavelab.quantity_presets import QuantityLibrary, QUANTITY_PRESETS, conversion_factor
from wavelab.channel_properties_ui import apply_channel_table
from wavelab.units import confirmed_y_axis

ROOT = Path(__file__).resolve().parents[1]


def work(tmp_path):
    w=Workbench(tmp_path)
    p=ROOT/'test/fixtures/X相下桥臂故障电流.txt'
    w.import_bytes(p.read_bytes(),p.name)
    return w


def test_dropdown_columns_are_real_and_batch_is_collapsed(tmp_path):
    w=work(tmp_path)
    at=AppTest.from_file(ROOT/'app.py',default_timeout=45)
    at.session_state['workbench']=w
    at.run(); assert not at.exception
    assert at.get('component_instance')
    assert not any(e.label in ('批量单位','自定义单位','Y轴物理量预设') for e in at.text_input)



@pytest.mark.parametrize('pid,units',[
    ('current',['kA','A','mA','pu']),('voltage',['kV','V','mV','pu']),
    ('active_power',['MW','kW','W','pu']),('reactive_power',['Mvar','kvar','var','pu']),
    ('apparent_power',['MVA','kVA','VA','pu']),('frequency',['Hz','kHz','pu']),
    ('phase_angle',['°','rad']),('impedance',['Ω','mΩ','pu']),
    ('energy',['MJ','kJ','J','kWh']),('temperature',['℃','K']),('per_unit',['pu','1'])])
def test_requested_choices(pid,units):
    assert set(units)<=set(QUANTITY_PRESETS[pid].units)


def test_switch_is_unitless_and_bilingual(tmp_path):
    w=work(tmp_path); c=w.spec.datasets[0].channels[0]
    w.set_channel_properties({c.channel_id:dict(quantity_name='switch_state',unit=None)})
    w.assign_channels('panel_1',[c.channel_id])
    assert confirmed_y_axis(w.spec,w.spec.panels[0],'zh')==('开关状态',None)
    assert confirmed_y_axis(w.spec,w.spec.panels[0],'en')==('Switch state',None)
    with pytest.raises(ValueError,match='无单位'):
        w.set_channel_properties({c.channel_id:dict(unit='A')})


def test_preserve_custom_choices_and_reject_incompatible_with_suggestion(tmp_path):
    w=work(tmp_path); c=w.spec.datasets[0].channels[0]
    w.set_channel_properties({c.channel_id:dict(quantity_name='历史自定义量',unit='legacy_unit')})
    saved=w.save_project('custom'); w.open_project(saved)
    c=w.spec.datasets[0].channels[0]
    assert c.quantity.zh=='历史自定义量' and c.unit=='legacy_unit'
    raw=next(iter(w.data.values())).samples.copy()
    w.set_channel_properties({c.channel_id:dict(quantity_name='current',unit='kA')})
    before=w.spec
    with pytest.raises(ValueError,match='推荐选择 kV'):
        w.set_channel_properties({c.channel_id:dict(quantity_name='voltage',unit='kA')})
    assert w.spec==before
    w.set_channel_properties({c.channel_id:dict(quantity_name='voltage',unit='kV')})
    np.testing.assert_array_equal(raw,next(iter(w.data.values())).samples)


def test_table_edit_batch_and_duplicate_identity(tmp_path):
    w=work(tmp_path); m=w.spec.datasets[0]
    rows=[dict(channel_id=c.channel_id,display_name=c.display_name,quantity_name='',unit=c.unit) for c in m.channels]
    rows[0].update(display_name='A相电流',quantity_name='current',unit='kA')
    apply_channel_table(w,m,dict(binding=w.project_epoch,revision=w.revision,rows=rows))
    ids=[c.channel_id for c in m.channels[:3]]
    for i,row in enumerate(rows[:3]):
        row.update(display_name=['A相电流','B相电流','C相电流'][i],quantity_name='current',unit='kA')
    apply_channel_table(w,w.spec.datasets[0],dict(binding=w.project_epoch,revision=w.revision,rows=rows))
    w.assign_channels('panel_1',ids)
    assert confirmed_y_axis(w.spec,w.spec.panels[0],'zh')[0]=='电流 (kA)'
    assert confirmed_y_axis(w.spec,w.spec.panels[0],'en')[0]=='Current (kA)'
    saved=w.save_project('table'); fresh=Workbench(tmp_path/'fresh');fresh.open_project(saved)
    assert [c.display_name for c in fresh.spec.datasets[0].channels[:3]]==['A相电流','B相电流','C相电流']


def test_pu_metadata_and_temperature_never_imply_conversion(tmp_path):
    w=work(tmp_path); c=w.spec.datasets[0].channels[0]
    for pid in ('active_power','reactive_power','apparent_power','frequency'):
        w.set_channel_properties({c.channel_id:dict(quantity_name=pid,unit='pu')})
    with pytest.raises(ValueError): conversion_factor('pu','MW')
    with pytest.raises(ValueError): conversion_factor('℃','K')
    assert conversion_factor('℃','°C')==1


def test_old_custom_name_matching_builtin_is_not_replaced(tmp_path):
    w=work(tmp_path); m=w.spec.datasets[0]; cid=m.channels[0].channel_id
    w.edit_channels(m.dataset_id,{cid:dict(unit='arb',quantity=dict(
        zh='电流',en='My calibrated quantity',unit='arb',confirmation_source='historical'))})
    w.set_channel_properties({cid:dict(display_name='新名称',quantity_name='电流',unit='arb')})
    quantity=w.spec.datasets[0].channels[0].quantity
    assert quantity.en=='My calibrated quantity' and quantity.preset_id is None

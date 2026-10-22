import pytest
from wavelab.workbench import Workbench
from wavelab.units import confirmed_y_axis

@pytest.mark.parametrize('language,title',[('zh','电压 (kV)'),('en','Voltage (kV)')])
def test_axis_information_has_only_channel_authority(tmp_path,language,title):
    w=Workbench(tmp_path);w.import_bytes(b'Domain,u,u\n0,1,2\n1,3,4','sample.txt')
    ids=[c.channel_id for c in w.spec.datasets[0].channels];w.assign_channels('panel_1',ids)
    assert confirmed_y_axis(w.spec,w.spec.panels[0],language)[1]
    w.set_channel_properties({cid:dict(quantity_name='voltage',unit='kV') for cid in ids})
    assert confirmed_y_axis(w.spec,w.spec.panels[0],language)==(title,None)
    with pytest.raises(ValueError):w.update(['panels',0,'ylabel_i18n'],dict(en='Wrong current'))
    w.set_channel_properties({ids[0]:dict(quantity_name='current',unit='kA')})
    assert confirmed_y_axis(w.spec,w.spec.panels[0],language)[1]

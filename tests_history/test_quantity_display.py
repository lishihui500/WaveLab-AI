"""Automatic quantity/unit display replaces independent axis overrides."""
import numpy as np
import pytest
from wavelab.workbench import Workbench
from wavelab.render.engine import render_figure

@pytest.mark.parametrize('preset,large,small,factor',[
    ('voltage','kV','V',.001),('current','kA','A',.001),
    ('active_power','MW','W',1e-6),('inductance','H','mH',.001),
    ('capacitance','F','μF',1e-6),('resistance','Ω','mΩ',.001)])
def test_mixed_prefixes_convert_only_display_arrays(tmp_path,preset,large,small,factor):
    w=Workbench(tmp_path);w.import_bytes(b'Domain,x,x\n0,1000,2\n1,2000,3','sample.txt')
    ids=[c.channel_id for c in w.spec.datasets[0].channels]
    w.set_channel_properties({ids[0]:dict(quantity_name=preset,unit=small),ids[1]:dict(quantity_name=preset,unit=large)})
    w.assign_channels('panel_1',ids)
    raw=next(iter(w.datasets.values())).samples.copy()
    image=render_figure(w.spec,w.datasets)
    np.testing.assert_allclose(image.lines['panel_1',ids[0]].get_ydata(),raw[:,1]*factor)
    np.testing.assert_array_equal(next(iter(w.datasets.values())).samples,raw)
    with pytest.raises(ValueError):w.set_display_unit('panel_1',small)

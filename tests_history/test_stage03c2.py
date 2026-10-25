"""3C.2 synthetic local acceptance; no external model calls."""
import json
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from wavelab.workbench import Workbench
from wavelab.ai.manual import ManualExchange, task_context, protocol
from wavelab.ai.assistant import figure_context
from wavelab.units import unit_status
from wavelab.render.engine import render_figure
from test_manual import response, patch, w




@pytest.mark.parametrize('same', [False,True])
def test_same_leaf_conflict_or_idempotence(w,same):
    e=ManualExchange(); e.generate(w,'红色')
    raw=response(e,[patch(w,color='red')]); w.update(['panels',0,'series',0,'color'],'red' if same else 'blue')
    before=w.spec
    # Strict snapshot protocol supersedes the former idempotent merge behavior.
    with pytest.raises(ValueError, match='过期'):
        e.validate(w, raw)
    assert w.spec == before



@pytest.mark.parametrize('change',['deleted','unit','mapping','move','event','undo'])
def test_dependencies(w,change):
    e=ManualExchange(); e.generate(w,'局部修改')
    raw=response(e,[dict(action='set_time_axis',changes={'xlim':[0,1]})] if change=='event' else [patch(w,color='red')])
    if change=='deleted': w.assign_channels('panel_1',[])
    elif change=='unit': w.edit_channels(w.spec.datasets[0].dataset_id,{w.spec.panels[0].series[0].channel_id:{'unit':'V'}, w.spec.panels[0].series[1].channel_id:{'unit':'V'}})
    elif change=='mapping': w.map_channels(w.spec.datasets[0].dataset_id,'u','numbered','changed','kV')
    elif change=='move':
        from wavelab.domain.figure import PanelSpec
        w.update(['panels'],[p.model_dump(mode='json') for p in w.spec.panels]+[PanelSpec(id='p2').model_dump(mode='json')]); w.move_series('panel_1',w.spec.panels[0].series[0].channel_id,'p2')
    elif change=='event':w.update(['time_axis','unit'],'ms')
    else: w.undo(); w.redo()
    before=w.spec
    with pytest.raises(ValueError):e.validate(w,raw)
    assert w.spec==before




def test_explicit_noop_cannot_overwrite_manual(w):
    e=ManualExchange();e.generate(w,'恢复颜色');raw=response(e,[patch(w,color=None)])
    w.update(['panels',0,'series',0,'color'],'blue')
    with pytest.raises(ValueError,match='过期'):e.validate(w,raw)












def test_time_unit_preserves_physical_window_and_auto_title(w):
    w.update(['time_axis','xlim'],[0.5,1.5])
    samples=next(iter(w.datasets.values())).samples.copy()
    w.set_time_unit('ms')
    assert w.spec.time_axis.xlim==(500,1500)
    assert render_figure(w.spec,w.datasets).figure.axes[0].get_xlabel()=='时间 (ms)'
    w.undo();assert w.spec.time_axis.xlim==(0.5,1.5)
    np.testing.assert_array_equal(samples,next(iter(w.datasets.values())).samples)






def test_second_confirmation_detects_new_conflict(w):
    e=ManualExchange();e.generate(w,'红色');e.validate(w,response(e,[patch(w,color='red')]))
    w.update(['panels',0,'series',0,'color'],'blue');before=w.spec
    with pytest.raises(ValueError,match='过期'):e.apply(w)
    assert w.spec==before








def test_parent_range_replacement_conflicts_with_child_edit(w):
    w.update(['panels',0,'ylim'],[0,10])
    e=ManualExchange();e.generate(w,'自动范围')
    raw=response(e,[dict(action='update_panel',panel_id='panel_1',changes={'ylim':None})])
    w.update(['panels',0,'ylim'],[0,20]);before=w.spec
    with pytest.raises(ValueError,match='过期'):e.validate(w,raw)
    assert w.spec==before




def test_legend_sync_request_is_already_satisfied(w):
    context,selected=task_context(w,'将曲线的图例名称与通道名称一致')
    assert selected=={'query_context'}
    assert context['datasets']

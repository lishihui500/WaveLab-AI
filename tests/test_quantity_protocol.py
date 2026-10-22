"""Canonical channel metadata protocol; no per-axis/series definitions."""
import asyncio
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from time import monotonic,sleep
import pytest
from wavelab.local_bridge import execute,status,Bridge
from wavelab.commands.plot import Plan,prepare,apply_proposal,tool_definitions
from wavelab.mcp_server import create_server
from wavelab.workbench import Workbench

def work(tmp_path):
    w=Workbench(tmp_path);w.import_bytes(b'Domain,u\n0,25000\n0.1,26000\n0.2,24000','sample.txt')
    cid=w.spec.datasets[0].channels[0].channel_id;w.assign_channels('panel_1',[cid])
    w.set_channel_preset(cid,'voltage','V');return w

def test_json_actions_and_mcp_schema(tmp_path):
    w=work(tmp_path);cid=w.spec.datasets[0].channels[0].channel_id
    p=Plan.model_validate(dict(summary='统一属性',actions=[dict(action='set_channel_properties',channel_id=cid,evidence_quote='源单位 kV',changes=dict(quantity_name='voltage',unit='kV'))]))
    apply_proposal(w,prepare(w,p,'源单位 kV'))
    context=execute(w,'gui','get_figure_context',{})['context']
    assert context['datasets'][0]['channels'][0]['unit']=='kV'
    assert 'display_unit' not in context['panels'][0]
    assert 'label_i18n' not in context['panels'][0]['series'][0]
    schema=tool_definitions()
    assert 'set_channel_properties' in schema['allowed_changes']
    assert not {'set_axis_quantity','set_display_unit','configure_panel_quantity'} & schema['allowed_changes'].keys()

@pytest.mark.parametrize('changes,quote,user_text',[
    ({'unit':'V'},None,'源单位 V'),({'unit':'V'},'源单位 V','源单位 kV'),
    ({'quantity_name':'current','unit':'kV'},'源单位 kV','源单位 kV'),
    ({'display_name':''},None,'改名'),({'source_column_index':2},None,'更改索引')])
def test_invalid_metadata_is_atomic(tmp_path,changes,quote,user_text):
    w=work(tmp_path);before=w.spec
    p=Plan.model_validate(dict(summary='bad',actions=[dict(action='set_channel_properties',channel_id=w.spec.datasets[0].channels[0].channel_id,evidence_quote=quote,changes=changes)]))
    with pytest.raises(ValueError):prepare(w,p,user_text)
    assert w.spec==before

@pytest.mark.parametrize('action',['set_axis_quantity','set_display_unit','configure_panel_quantity'])
def test_retired_axis_write_operations_are_not_parseable(action):
    with pytest.raises(ValueError):Plan.model_validate(dict(summary='legacy',actions=[dict(action=action,panel_id='panel_1',changes={})]))

def test_unified_real_mcp_tool_to_loopback_bridge(tmp_path):
    w=work(tmp_path);bridge=Bridge(tmp_path/'runtime');bridge.attach('gui');before=w.spec;current=status(w,'gui')
    async def invoke():
        server=create_server(tmp_path/'runtime')
        result=await server.call_tool('apply_plot_actions',dict(session_id='gui',expected_project_epoch=w.project_epoch,expected_revision=w.revision,
            expected_fingerprint=current['fingerprint'],user_request='源单位 kV',actions=[dict(action='set_channel_properties',channel_id=w.spec.datasets[0].channels[0].channel_id,
            evidence_quote='源单位 kV',changes=dict(quantity_name='voltage',unit='kV'))]))
        return json.loads(result[0].text)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(asyncio.run,invoke());deadline=monotonic()+20
            while not future.done():
                bridge.drain('gui',w);assert monotonic()<deadline;sleep(.01)
            result=future.result()
        assert result['result']['samples_unchanged']
        assert w.spec.datasets[0].channels[0].unit=='kV'
        w.undo();assert w.spec==before
    finally:bridge.close()

def test_fresh_stdio_exposes_only_canonical_channel_metadata():
    import sys
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    async def check():
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','wavelab.mcp_server'])) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize()
                result=await session.call_tool('get_plot_action_schema',{})
                schema=json.loads(result.content[0].text)
                assert 'set_channel_properties' in schema['change_fields']
                assert 'set_axis_quantity' not in schema['change_fields']
    asyncio.run(check())


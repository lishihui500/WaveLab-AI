import importlib.util,json,time
from pathlib import Path
import pytest
s=importlib.util.spec_from_file_location('infra',Path(__file__).parents[1]/'scripts/stage04_infra_v2.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
READY={k:True for k in ['independent_context','direct_tools','logging_ready','deadline_ready']}
def result(body,error=False):return {'content':[{'type':'text','text':json.dumps(body)}],'isError':error}
def test_real_formal_parameter_error_is_lossless():
 p=Path(__file__).parents[1]/'reports/stage_04/formal/MCP_T2_R1/broker/0003_apply_plot_actions.json';record=json.loads(p.read_text(encoding='utf-8'));parsed=m.parse_result(record['result']);assert parsed['is_error'] is True and parsed['body'] is None and parsed['raw']==record['result'];assert m.assemble([record])['tool_error_count']==1
@pytest.mark.parametrize('raw',[None,[],{}, {'content':[]},{'content':[{'type':'image','data':'opaque'}]}, {'content':[{'type':'text','text':'not JSON'},{'type':'text','text':'second block'}]}])
def test_non_json_or_missing_content_never_crashes(raw): assert m.parse_result(raw)['raw']==raw

def test_actual_validation_error_and_applied_are_separate():
 reject={'tool':'apply_plot_actions','result':result({'error':'validation_error'})};ok={'tool':'apply_plot_actions','result':result({'result':{'status':'applied'}})};r=m.assemble([reject,ok]);assert r['validation_rejection_count']==1 and r['applied_count']==1 and r['raw_records']==[reject,ok]
def test_error_flag_prevents_false_applied():assert m.assemble([{'tool':'apply_plot_actions','result':result({'result':{'status':'applied'}},True)}])['applied_count']==0
def test_parser_does_not_mutate():
 raw=result({'context':{'x':1}});p=m.parse_result(raw);p['raw']['isError']=True;assert raw['isError'] is False

def test_preflight_prevents_early_release(tmp_path):
 g=m.DispatchGate(tmp_path,1)
 try:
  with pytest.raises(m.PreflightIncomplete):g.release({**READY,'direct_tools':False})
  assert not g.started
 finally:g.finish()
def test_second_release_refused(tmp_path):
 g=m.DispatchGate(tmp_path,1)
 try:
  g.release(READY)
  with pytest.raises(RuntimeError):g.release(READY)
 finally:g.finish()
def test_watchdog_closes_without_model_polling(tmp_path):
 g=m.DispatchGate(tmp_path,.04);called=[]
 try:
  g.release(READY);time.sleep(.1);assert g.closed.is_set()
  with pytest.raises(m.DeadlineExceeded):g.dispatch('late',lambda:called.append(1))
  assert called==[]
 finally:g.finish()
 events=[json.loads(s) for s in (tmp_path/'events.jsonl').read_text().splitlines()];assert any(v['event']=='deadline_reached' for v in events)
def test_late_inflight_result_retained_but_new_call_denied(tmp_path):
 g=m.DispatchGate(tmp_path,.03)
 try:
  g.release(READY);assert g.dispatch('slow',lambda:(time.sleep(.08),{'real_value':7})[1])=={'real_value':7}
  with pytest.raises(m.DeadlineExceeded):g.dispatch('next',lambda:None)
 finally:g.finish()
 events=[json.loads(s) for s in (tmp_path/'events.jsonl').read_text().splitlines()];assert any(v['event']=='tool_returned' and v['late'] and v['result']=={'real_value':7} for v in events)
def test_tool_exception_retains_error(tmp_path):
 g=m.DispatchGate(tmp_path,1)
 try:
  g.release(READY)
  with pytest.raises(ValueError):g.dispatch('bad',lambda:(_ for _ in ()).throw(ValueError('test failure')))
 finally:g.finish()
 assert 'test failure' in (tmp_path/'events.jsonl').read_text()
def test_existing_evidence_not_truncated(tmp_path):
 (tmp_path/'events.jsonl').write_text('keep')
 with pytest.raises(FileExistsError):m.DispatchGate(tmp_path,1)
 assert (tmp_path/'events.jsonl').read_text()=='keep'

"""Stage4 infrastructure v2: lossless result parsing and dispatch deadlines.
No plotting, GUI automation or task scoring is implemented here.
"""
from __future__ import annotations
import copy,json,time,threading,datetime
from pathlib import Path

def parse_result(raw):
    original=copy.deepcopy(raw)
    if not isinstance(raw,dict):
        return {'kind':'non_object','is_error':None,'body':None,'raw':original}
    content=raw.get('content');texts=[];parsed=[]
    if isinstance(content,list):
        for block in content:
            if isinstance(block,dict) and block.get('type')=='text' and isinstance(block.get('text'),str):
                value=block['text'];texts.append(value)
                try: parsed.append(json.loads(value))
                except (json.JSONDecodeError,ValueError): pass
    body=parsed[0] if len(texts)==1 and len(parsed)==1 and isinstance(parsed[0],dict) else None
    error=raw.get('isError') if isinstance(raw.get('isError'),bool) else None
    if body is not None and body.get('error'): error=True
    kind='json_object' if body is not None else ('text_or_mixed' if texts else 'no_text')
    return {'kind':kind,'is_error':error,'body':body,'texts':texts,'raw':original}

def assemble(records):
    rows=copy.deepcopy(records)
    normalized=[{'record':r,'parsed':parse_result(r.get('result'))} for r in rows]
    contexts=[x for x in normalized if x['record'].get('tool')=='get_figure_context' and isinstance((x['parsed'].get('body') or {}).get('context'),dict)]
    rejected=[x for x in normalized if x['record'].get('tool')=='apply_plot_actions' and (x['parsed'].get('body') or {}).get('error')=='validation_error']
    errors=[x for x in normalized if x['parsed']['is_error'] is True]
    applied=[x for x in normalized if x['record'].get('tool')=='apply_plot_actions' and x['parsed']['is_error'] is not True and ((x['parsed'].get('body') or {}).get('result') or {}).get('status')=='applied']
    return {'schema_version':'infra-v2','raw_records':rows,'normalized_records':normalized,'tool_error_count':len(errors),'validation_rejection_count':len(rejected),'applied_count':len(applied),'first_context':contexts[0]['record']['result'] if contexts else None,'last_context':contexts[-1]['record']['result'] if contexts else None,'complete_assembly':True,'task_success':'NOT_SCORED'}

class DeadlineExceeded(RuntimeError):pass
class PreflightIncomplete(RuntimeError):pass

class DispatchGate:
    """Blocks NEW calls after deadline; late in-flight results are preserved.

    The callable must be an actual tool adapter for end-to-end use. Unit tests
    with counters/sleeps establish only component behavior, never GUI results.
    """
    def __init__(self,folder,budget_s,*,clock=time.monotonic,watch_interval_s=.005):
        if budget_s<=0:raise ValueError('budget must be positive')
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/'events.jsonl'
        self.stream=self.path.open('x',encoding='utf-8')
        self.budget_s=float(budget_s);self.clock=clock;self.interval=watch_interval_s
        self.lock=threading.RLock();self.closed=threading.Event();self.stop=threading.Event();self.started=False;self.seq=0
        self.worker=None
    def log(self,event,**payload):
        with self.lock:
            self.seq+=1;row={'seq':self.seq,'event':event,'monotonic_s':self.clock(),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**payload}
            self.stream.write(json.dumps(row,ensure_ascii=False)+'\n');self.stream.flush()
            return row
    def release(self,checks):
        required=['independent_context','direct_tools','logging_ready','deadline_ready']
        if not all(checks.get(k) is True for k in required):
            self.log('release_refused',checks=checks);raise PreflightIncomplete('all preflight gates must be verified before release')
        with self.lock:
            if self.started:raise RuntimeError('already released')
            self.started=True;self.start=self.clock();self.deadline=self.start+self.budget_s
            self.log('released',budget_s=self.budget_s,deadline_monotonic_s=self.deadline)
        self.worker=threading.Thread(target=self._watch,daemon=True);self.worker.start()
    def _expire(self):
        with self.lock:
            if not self.closed.is_set():
                self.closed.set();self.log('deadline_reached',deadline_monotonic_s=self.deadline,censored_s=self.budget_s)
    def _watch(self):
        while not self.stop.wait(self.interval):
            if self.clock()>=self.deadline:self._expire();return
    def dispatch(self,request_id,callable_,*,request=None):
        with self.lock:
            if not self.started:raise PreflightIncomplete('not released')
            if self.clock()>=self.deadline:self._expire()
            if self.closed.is_set():
                self.log('dispatch_refused',request_id=request_id,request=request,reason='deadline');raise DeadlineExceeded(request_id)
            self.log('dispatch_started',request_id=request_id,request=request)
        try: result=callable_()
        except Exception as exc:
            self.log('tool_exception',request_id=request_id,error_type=type(exc).__name__,message=str(exc),late=self.clock()>=self.deadline);raise
        late=self.clock()>=self.deadline
        if late:self._expire()
        self.log('tool_returned',request_id=request_id,late=late,result=result)
        return result
    def finish(self):
        self.stop.set()
        if self.worker:self.worker.join(timeout=1)
        self.stream.close()

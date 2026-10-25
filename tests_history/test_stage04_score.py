import copy, importlib.util
from pathlib import Path
s=importlib.util.spec_from_file_location('scorer',Path(__file__).parents[1]/'scripts/stage04_score.py')
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
E={k:True for k in ['source_bytes','arrays','identity','save_reopen','render_geometry','visual_review']}
C=[{'id':'color','path':'/panels/0/color','equals':'#D55E00'}]
B={'panels':[{'color':'#0072B2','width':1.2}],'data':'immutable'}
def good():
 a=copy.deepcopy(B);a['panels'][0]['color']='#D55E00';return a

def test_valid(): assert m.score(B,good(),C,E)['strict_pass']
def test_orange_mismatch():
 a=good();a['panels'][0]['color']='#E69F00';assert not m.score(B,a,C,E)['strict_pass']
def test_non_target():
 a=good();a['data']='changed';assert m.score(B,a,C,E)['unexpected_paths']==['/data']
def test_missing_evidence(): assert not m.score(B,good(),C,{})['strict_pass']
def test_failed_array_check(): assert not m.score(B,good(),C,{**E,'arrays':False})['strict_pass']
def test_duplicate_panel():
 a=good();a['panels'].append(a['panels'][0]);assert not m.score(B,a,C,E)['strict_pass']
def test_missing_target():
 a=good();del a['panels'][0]['color'];assert not m.score(B,a,C,E)['strict_pass']
def test_empty_constraints(): assert not m.score(B,B,[],E)['strict_pass']
def test_no_mutation():
 b=copy.deepcopy(B);a=good();original=copy.deepcopy(a);m.score(b,a,C,E);assert b==B and a==original

def test_t4_requires_intermediate_evidence(): assert not m.score(B,good(),C,E,task_id='T4')['strict_pass']
def test_container_transition():
 b={'x':None};a={'x':[1.4,1.6]};c=[{'id':str(i),'path':p,'equals':v} for i,(p,v) in enumerate(m.leaves(a).items())];assert m.score(b,a,c,E)['strict_pass']
def test_extra_leaf_after_transition():
 b={'x':None};a={'x':[1.4,1.6,1.8]};c=[{'id':'x0','path':'/x/0','equals':1.4}];assert not m.score(b,a,c,E)['strict_pass']

def test_t2_requires_unique_id_evidence(): assert not m.score(B,good(),C,E,task_id='T2')['strict_pass']
def test_t2_unique_id_evidence_pass(): assert m.score(B,good(),C,{**E,'inset_ids_unique':True},task_id='T2')['strict_pass']

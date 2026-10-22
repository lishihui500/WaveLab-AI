"""Audit delivered evidence consistency. No plotting actions or acceptance relaxation."""
from pathlib import Path
import csv,hashlib,json,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/stage_03F'
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))
required=['stage_03F_A_report.md','benchmark_protocol.md','benchmark_results.csv','benchmark_results.json','performance_analysis.md','correctness_report.md','issues_and_fixes.md','limitations.md','manual_test_guide.md','manual_test_record_template.csv','manual_timer.html','course_report_draft.md','architecture.md','demo_cases.md','mcp_trace.json','agent_mcp_trace.json','gui_events.json','gui_timing.json','gui_event_assignment.json','visual_review.json','review_approved_pixels.json','requirements_snapshot.txt','supplemental_initial_manifest.json','gui_final_preview.png']
assert all((OUT/name).is_file() for name in required)
records=read('benchmark_results.json')['records'];automated=[r for r in records if r['method'] in ['codex_mcp','gui_automation']];human=[r for r in records if r['method'] in ['manual_gui','chatgpt_json']]
assert len(automated)==19 and len(human)==6
assert all(r['status']=='NOT_MEASURED' and not r.get('timing') for r in human)
assert sum(r['final_success'] for r in automated)==16
for method in ['codex_mcp','gui_automation']:
 for task in ['F01','F02','F03']:
  rows=[r for r in automated if r['method']==method and r['task_id']==task]
  assert sum(r['timing']['task_s'] is not None for r in rows)==3
for task in ['F01','F02','F03']:assert len({r['baseline_semantic_hash'] for r in automated if r['task_id']==task})==1
assert not read('statistics.json')['same_boundary_ratios']
assert read('source_integrity.json')['passed'] and read('product_source_integrity.json')['all_unchanged']
assert all(row['equivalent'] for row in read('supplemental_initial_manifest.json'))
assert all(row['dom_project_matches'] for row in read('gui_event_assignment.json'))
approved=set(read('review_approved_pixels.json')['approved_pixel_sha256'])
assert all(g['pixel_sha256'] in approved for g in read('image_equivalence_groups.json'))
for row in automated:
 a=read(row['evidence']['acceptance']);assert a['passed']==row['final_success']
 assert row['checks']['data'] and row['checks']['saved_reopened'] and row['checks']['visual']
with (OUT/'benchmark_results.csv').open(encoding='utf-8-sig',newline='') as f:assert len(list(csv.DictReader(f)))==25
with (OUT/'manual_test_record_template.csv').open(encoding='utf-8-sig',newline='') as f:
 rows=list(csv.DictReader(f));assert len(rows)==6 and all(r['status']=='NOT_MEASURED' and r['method'] in ['manual_gui','chatgpt_json'] for r in rows)
root=ET.parse(OUT/'pytest_final.xml').getroot();suites=[root] if root.tag=='testsuite' else list(root)
assert sum(int(s.get('tests',0)) for s in suites)==399
assert all(int(s.get('failures',0))==int(s.get('errors',0))==int(s.get('skipped',0))==0 for s in suites)
for stem in ['task_times','mcp_calls','success_counts']:
 for fmt in ['png','pdf','svg']:assert (OUT/'figures'/f'{stem}.{fmt}').is_file()
trace=read('mcp_trace.json');agent=read('agent_mcp_trace.json')['traces'];assert len(trace)+len(agent)==42
for r in automated:
 if r['method']!='codex_mcp':continue
 key=r['trial_id'].removeprefix('MCP_');entries=[x for x in trace if x['trial']==key]+[x for x in agent if x['round']==key]
 duration=sum(x['duration_s'] if 'duration_s' in x else (x['end_ms']-x['start_ms'])/1000 for x in entries)
 assert len(entries)==r['mcp_calls'] and abs(duration-r['timing']['mcp_total_s'])<.002
manifest=[]
for p in OUT.rglob('*'):
 if p.is_file() and p.name not in ['delivery_manifest.json','delivery_validation.json','server_stdout.log','server_stderr.log']:
  manifest.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
for p in sorted((ROOT/'scripts').glob('stage03f_*')):
 if p.is_file():manifest.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
for p in [ROOT/'tests/test_stage03f_acceptance.py']:
 manifest.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(OUT/'delivery_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
result=dict(passed=True,automated_records=19,human_not_measured=6,strict_successes=16,strict_failures=3,mcp_calls=42,pytest_passed=399,manifest_files=len(manifest),notes=['Interrupted GUI F01 R1 retained, entire duration excluded; R4 independently added.','No same-boundary speedup ratio.','Raw logs and failed projects preserved.'])
(OUT/'delivery_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result))

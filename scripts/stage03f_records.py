"""Derive records from immutable measured timestamps, saved states and actual image review."""
from pathlib import Path
import hashlib,json
from datetime import datetime,timezone
from PIL import Image

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/stage_03F'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def iso(ms):return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()
def milliseconds(s):return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000
def cost(e):return 2 if e['kind'] in ['select','fill','number','combo'] else 1

def main():
    # Root actually inspected review_sheets/sheet_01..06 in this chat after final export.
    groups=read(OUT/'image_equivalence_groups.json')
    approved=read(OUT/'review_approved_pixels.json')
    unknown={g['pixel_sha256'] for g in groups}-set(approved['approved_pixel_sha256'])
    if unknown:raise ValueError('New pixels require actual visual inspection before approval: '+str(unknown))
    reviewed={g['group_id']:dict(status='PASS_LEGIBILITY',sheet=g['review_sheet'],representative=g['representative'],pixel_sha256=g['pixel_sha256'],basis='Actual root Codex visual inspection of all six contact sheets; prior full-size representative PNG/PDF raster checks also retained') for g in groups}
    dump(OUT/'visual_review.json',dict(reviewer='root Codex',groups=reviewed,notes=['PNG and PDF raster, Chinese and English all covered by exact pixel equivalence groups.','GUI F03 R1 contains two coincident B insets: legibility alone does not detect the configuration error; overall task FAIL.','Insets cover a portion of repeated synthetic steady-state waves; no confirmed fault-critical region was present to assess.']))
    membership={member:g['group_id'] for g in groups for member in g['members']}
    events=read(OUT/'gui_events.json');times=read(OUT/'gui_timing.json')
    assignments=[]
    for row in times:
        trial=row['trial'];task=trial.split('_')[1];folder=OUT/'artifacts'/trial.replace('GUI_','gui_')
        a=read(folder/'acceptance.json')
        selected=[(i,e) for i,e in enumerate(events) if row['start']<=milliseconds(e['started_at'])<row['end']]
        interrupted=trial=='GUI_F01_R1';partial=row.get('retries',0)>0
        first_edit=min((milliseconds(e['started_at']) for _,e in selected),default=None)
        count=sum(cost(e) for _,e in selected)
        expected_project=trial.removeprefix('GUI_')
        dom_checks=[]
        for i,e in selected:
            section=e.get('dom','').split('textbox "工程名称"',1)[-1][:300]
            project=section.split('- text: ',1)[-1].split('\n')[0] if '- text: ' in section else None
            if project is None and '- textbox: '+expected_project in e.get('dom','').splitlines():
                project=expected_project  # Active listbox temporarily makes background labels inaccessible.
            dom_checks.append(project==expected_project)
            assignments.append(dict(event_index=i,assigned_trial=trial,raw_trial_label=e.get('trial'),dom_project=project,dom_project_matches=project==expected_project,basis='Half-open measured wall-clock interval [start,end) plus recorded DOM project name; raw closure-captured label is not trusted'))
        if not all(dom_checks):raise ValueError('Recorded DOM project mismatch in '+trial)
        baseline=read(OUT/'baselines'/task/'project.json')['figure']
        digest=hashlib.sha256(json.dumps(baseline,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        notes=['Real visible GUI controls only; no MCP plotting or internal Workbench calls used for task edits.','GUI task interval starts at initial-ready marker before task edits and ends after final DOM read; may contain agent/tool orchestration.','Full save/reopen/export/image QA occurred later; complete end_to_end_s is not measured.','Raw helper interaction_count=0 and raw event trial labels were a closure-capture logging defect. Counts here derive directly from event timestamps, kind and DOM; raw logs preserved.','Rerun count and pure renderer latency are unavailable, not inferred.']
        if interrupted:notes+=['First F01 trial spans session pause: retain 48442.411 seconds raw wall time, exclude entire observation from performance statistics; replacement R4 uses fresh baseline.']
        if partial:notes+=['Failed UI attempts were not all captured by successful-action helper. interaction_count is null; recorded_successful_interaction_count is a lower bound.']
        if row.get('notes'):notes.append(row['notes'])
        if trial=='GUI_F03_R1':notes.append('Independent acceptance found two B insets after recovery. Preserve final FAIL; do not remove duplicate to rewrite this experiment.')
        record=dict(trial_id=trial,task_id=task,method='gui_automation',status='PASS' if a['passed'] else 'FAIL',first_attempt_success=a['passed'] and not partial,final_success=a['passed'],started_at=iso(row['start']),ended_at=iso(row['end']),timing=dict(task_s=None if interrupted else row['task_s'],end_to_end_s=None,mcp_total_s=None,apply_roundtrip_s=None,save_export_s=(row['gui_save_s']+row['gui_export_s']) if 'gui_save_s' in row and 'gui_export_s' in row else None,visual_check_s=None,page_load_s=row.get('page_load_s') if task!='F01' else None,render_s=None),timing_boundary_id='initial_ready_marker_to_final_visible',baseline_semantic_hash=digest,mcp_calls=0,interaction_count=None if partial else count,recorded_successful_interaction_count=count,retry_count=row.get('retries',0),parameter_errors=None,revision_conflict=None,human_intervention=False,rerun_count=None,timing_eligible=not interrupted,raw_wall_task_s=row['task_s'],editing_interval_s=None if interrupted or first_edit is None else (row['end']-first_edit)/1000,drawing_save_export_wall_s=row.get('drawing_save_export_wall_s'),preparation_load_wall_s=row.get('page_load_s') if task=='F01' else None,checks=dict(configuration=a['passed'],data=all(v for k,v in a['checks'].items() if k.startswith('data_') or 'samples' in k or 'arrays' in k),saved_reopened=a['checks']['save_close_reopen_spec'] and a['checks']['save_close_reopen_arrays'],geometry=all(v for k,v in a['checks'].items() if k.startswith('geometry_')),visual=True),failed_checks=[k for k,v in a['checks'].items() if not v],evidence=dict(acceptance=str((folder/'acceptance.json').relative_to(OUT)),events='gui_events.json',timing='gui_timing.json',visual_groups=[membership[str(p.relative_to(OUT))] for p in sorted(folder.glob('final_*.png'))]),notes=notes)
        screenshot=OUT/(trial+'.png')
        if screenshot.exists():record['screenshot_size_px']=list(Image.open(screenshot).size)
        dump(OUT/'trials'/trial/'record.json',record)
    dump(OUT/'gui_event_assignment.json',assignments)
    for p in (OUT/'trials').glob('MCP_*/record.json'):
        r=read(p);folder=OUT/'artifacts'/r['trial_id'].replace('MCP_','mcp_');a=read(folder/'acceptance.json')
        r.update(status='PASS' if a['passed'] else 'FAIL',first_attempt_success=a['passed'],final_success=a['passed'],transaction_success=True,failed_checks=[k for k,v in a['checks'].items() if not v])
        r['checks']=dict(configuration=a['passed'],data=all(v for k,v in a['checks'].items() if k.startswith('data_') or 'samples' in k or 'arrays' in k),saved_reopened=a['checks']['save_close_reopen_spec'] and a['checks']['save_close_reopen_arrays'],geometry=all(v for k,v in a['checks'].items() if k.startswith('geometry_')),visual=True)
        r['visual_review']=dict(status='PASS_LEGIBILITY',groups=[membership[str(q.relative_to(OUT))] for q in sorted(folder.glob('final_*.png'))],source='visual_review.json')
        r['validation_timing']=dict(save_reopen_s=a['save_reopen_seconds'],export_validation_s=a['export_validation_seconds'])
        note='Strict color protocol failed: natural language orange did not specify a hex code; #E69F00 chosen by model differs from validator #D55E00. Preserve strict FAIL as protocol ambiguity, not a proven language-understanding or product defect.'
        if r['failed_checks'] and note not in r['notes']:r['notes'].append(note)
        dump(p,r)
    print('Derived 10 GUI records and refreshed 9 MCP acceptance outcomes; raw logs unchanged.')

if __name__=='__main__':main()

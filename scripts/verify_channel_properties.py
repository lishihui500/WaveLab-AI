"""Real-case isolated acceptance; never writes the source project or inputs."""
from pathlib import Path
import hashlib
import json
import sys

from wavelab.workbench import Workbench
from wavelab.commands.plot import sample_hashes
from wavelab.render.engine import render_figure, export_figure
from wavelab.local_bridge import execute


def main():
    root = Path(__file__).resolve().parents[1]
    output = root/'reports/channel_properties_20261021'
    source = root/'.wavelab/projects/汇报绘图案例'
    def hashes(folder):
        return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob('*') if p.is_file()}
    original = hashes(source)
    work = Workbench(output/'acceptance')
    work.open_project(output/'baseline_project/project.json')
    arrays = sample_hashes(work)
    manifest = next(m for m in work.spec.datasets if len(m.channels)==3 and
                    all(c.quantity and c.quantity.en=='Current' and c.unit=='kA' for c in m.channels))
    ids = [c.channel_id for c in manifest.channels]
    work.create_panel('properties_validation')
    work.assign_channels('properties_validation', ids)
    data = work.datasets[manifest.dataset_id]
    work.upsert_inset('properties_validation',dict(id='properties_zoom',xlim_s=[1.32,1.34]))
    original_spec = work.spec
    work.set_channel_properties({cid:dict(display_name=f'电流{i+1}',quantity_name='current',unit='kA') for i,cid in enumerate(ids)})
    changed = work.spec
    work.undo(); assert work.spec==original_spec
    work.redo(); assert work.spec==changed
    assert arrays==sample_hashes(work)
    saved=work.save_project('real_case_verified')
    reopened=Workbench(output/'reopened');reopened.open_project(saved)
    assert arrays==sample_hashes(reopened)
    channels = {c.channel_id:c for m in reopened.spec.datasets for c in m.channels}
    image=render_figure(reopened.spec,reopened.datasets)
    for i,cid in enumerate(ids):
        assert channels[cid].display_name==f'电流{i+1}'
        assert image.lines[('properties_validation',cid)].get_label()==f'电流{i+1}'
        assert execute(reopened,'acceptance','get_channel_metadata',dict(channel_id=cid))['channel']['unit']=='kA'
    for extension in ('pdf','png','svg'):
        export_figure(image,output/f'real_case_verified.{extension}')
    assert original==hashes(source)
    report=dict(source_project_unchanged=True,source_file_hashes=original,
                samples_unchanged=arrays==sample_hashes(reopened),sample_hashes=arrays,
                three_current_channels=ids,undo_redo=True,save_reopen=True,
                metadata_readback=True,exports=['pdf','png','svg'],isolated_project=str(saved))
    (output/'acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('source_file_hashes','sample_hashes')},ensure_ascii=False))


if __name__=='__main__':
    main()

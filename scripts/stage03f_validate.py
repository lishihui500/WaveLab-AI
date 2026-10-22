"""Independent post-task acceptance/export. No task actions are generated or applied."""
from pathlib import Path
import argparse,copy,hashlib,json,shutil,subprocess,sys,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import numpy as np
from wavelab.workbench import Workbench
from wavelab.render.engine import render_figure,export_figure
from wavelab.quantity_presets import conversion_factor,time_factor
from matplotlib.colors import to_rgba
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/stage_03F'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,default=lambda value:value.item() if isinstance(value,np.generic) else str(value)),encoding='utf-8')
def normalize(spec):
    v=spec.model_dump(mode='json') if hasattr(spec,'model_dump') else copy.deepcopy(spec)
    for d in v['datasets']:d['source_path']=Path(d['source_path']).name
    return v
def load(path,root):
    w=Workbench(root);w.open_project(path);return w
def drawn_tick_labels(axis):
    """Use installed Matplotlib's exact Axis draw selection, including transforms.

    Axis._update_ticks returns the tick list consumed by Axis.draw; visible
    Text artists on cached out-of-window locator ticks are not actually drawn.
    """
    drawn=axis._update_ticks()
    selected={id(t) for t in drawn};excluded=[]
    for group,ticks in [('major',axis.get_major_ticks(len(axis.get_majorticklocs()))),('minor',axis.get_minor_ticks(len(axis.get_minorticklocs())))]:
        for tick in ticks:
            if id(tick) not in selected:
                excluded.append(dict(group=group,location=float(tick.get_loc()),reason='Not selected by installed Matplotlib Axis._update_ticks for actual draw (transformed view interval or inactive tick group)',view_interval=[float(v) for v in axis.get_view_interval()]))
    return [label for tick in drawn for label in [tick.label1,tick.label2] if label.get_visible()],excluded
def geometry_checks(r,view,language):
    """Pixel geometry from actual Agg artists, independent of visual judgment."""
    r.figure.canvas.draw();renderer=r.figure.canvas.get_renderer();fig=r.figure.bbox
    def coords(box):return [float(v) for v in box.extents]
    def inside(inner,outer,tol=1.):return bool(inner.x0>=outer.x0-tol and inner.y0>=outer.y0-tol and inner.x1<=outer.x1+tol and inner.y1<=outer.y1+tol)
    def overlaps(a,b):return bool(min(a.x1,b.x1)-max(a.x0,b.x0)>1 and min(a.y1,b.y1)-max(a.y0,b.y0)>1)
    result=dict(language=language,coordinate_system='Agg display pixels; 1 pixel numerical tolerance',figure_bbox=coords(fig),legends=[],texts=[],insets=[],excluded_ticks=[])
    mainboxes={key:ax.get_window_extent(renderer) for key,ax in r.axes.items()}
    for i,ax in enumerate(r.figure.axes):
        legend=ax.get_legend()
        if legend is None or not legend.get_visible():continue
        bbox=legend.get_window_extent(renderer)
        result['legends'].append(dict(artist_axis_index=i,bbox=coords(bbox),inside_figure=inside(bbox,fig),overlaps_main_axes=[key for key,box in mainboxes.items() if overlaps(bbox,box)]))
    for p in view.panels:
        ax=r.axes[p.id]
        text_items=[('title',ax.title),('xlabel',ax.xaxis.label),('ylabel',ax.yaxis.label)]
        for name,axis in [('xtick',ax.xaxis),('ytick',ax.yaxis)]:
            labels,excluded=drawn_tick_labels(axis)
            text_items += [(name,t) for t in labels]
            result['excluded_ticks'] += [dict(panel=p.id,axis=name,**row) for row in excluded]
        for kind,artist in text_items:
            if not artist.get_visible() or not artist.get_text().strip():continue
            bbox=artist.get_window_extent(renderer)
            result['texts'].append(dict(panel=p.id,kind=kind,text=artist.get_text(),bbox=coords(bbox),inside_figure=inside(bbox,fig)))
        for z in p.insets:
            child=r.inset_axes.get(z.id)
            if child is None:
                result['insets'].append(dict(panel=p.id,id=z.id,rendered=False,inside_parent=False,bounds_match=False));continue
            actual=child.get_window_extent(renderer);parent=mainboxes[p.id]
            relative=[(actual.x0-parent.x0)/parent.width,(actual.y0-parent.y0)/parent.height,actual.width/parent.width,actual.height/parent.height]
            result['insets'].append(dict(panel=p.id,id=z.id,rendered=True,bbox=coords(actual),parent_bbox=coords(parent),relative_bounds=relative,inside_parent=inside(actual,parent),bounds_match=bool(np.allclose(relative,z.bounds,rtol=0,atol=1e-10))))
    return result
def validate(task,path,folder,do_export=True):
    folder.mkdir(parents=True,exist_ok=True);started=time.perf_counter()
    baseline=OUT/'baselines'/task/'project.json'
    a=load(baseline,folder/'baseline_read');b=load(path,folder/'final_read')
    x=normalize(a.spec);y=normalize(b.spec);checks={}
    def check(name,condition):checks[name]=bool(condition)
    old=[s for p in x['panels'] for s in p['series']];new=[s for p in y['panels'] for s in p['series']]
    ids=[c['channel_id'] for c in x['datasets'][0]['channels']]
    check('three_ordered_phase_pairs',len(y['panels'])==3 and [[s['channel_id'] for s in p['series']] for p in y['panels']]==[ids[i:i+2] for i in range(0,6,2)])
    check('no_missing_or_duplicate_series',len(new)==6 and len({s['channel_id'] for s in new})==6)
    check('dataset_identity_metadata_unchanged',x['datasets']==y['datasets'])
    if task=='F01':
        check('series_properties_preserved',{s['channel_id']:s for s in old}=={s['channel_id']:s for s in new})
        check('shared_x_axis',y['share_time_axis'])
        check('outside_top_legend',y['legend']['location']=='outside_top')
        topx={k:v for k,v in x.items() if k not in ['panels','legend','share_time_axis']};topy={k:v for k,v in y.items() if k not in ['panels','legend','share_time_axis']}
        check('unrelated_top_fields_unchanged',topx==topy)
        check('unrelated_legend_fields_unchanged',{k:v for k,v in x['legend'].items() if k!='location'}=={k:v for k,v in y['legend'].items() if k!='location'})
        # New panels may omit explicit display_unit if their unchanged kV source
        # units yield exactly the same physical values and visible units.
        check('effective_units_preserved',all((p['display_unit'] or x['datasets'][0]['channels'][0]['unit'])=='kV' for p in y['panels']))
        check('panel_ranges_and_titles_preserved',all(all(p[k]==x['panels'][0][k] for k in ['title','title_i18n','ylim','xlim','scientific_y']) for p in y['panels']))
        check('no_unrequested_insets',all(not p['insets'] for p in y['panels']))
    elif task=='F02':
        check('exact_titles',all(p['title_i18n']==dict(zh=phase+'相',en='Phase '+phase) for p,phase in zip(y['panels'],'ABC')))
        check('exact_styles',all(s['color'].lower()==['#0072b2','#d55e00'][i%2] and s['linestyle']==['-','--'][i%2] and s['linewidth_pt']==1.2 for i,s in enumerate(new)))
        xx=copy.deepcopy(x);yy=copy.deepcopy(y)
        for v in [xx,yy]:
            for p in v['panels']:
                p.pop('title_i18n');p.pop('title')
                for s in p['series']:
                    for k in ['color','linestyle','linewidth_pt']:s.pop(k)
        check('all_unrelated_fields_unchanged',xx==yy)
    elif task=='F03':
        insets=[p['insets'] for p in y['panels']]
        check('one_inset_per_panel',all(len(z)==1 for z in insets))
        flat=[z[0] for z in insets if z]
        check('same_bounds',len(flat)==3 and len({tuple(z['bounds']) for z in flat})==1)
        check('exact_time_auto_y_own_channels',len(flat)==3 and all(z['xlim_s']==[1.4,1.44] and z['ylim'] is None and (not z['channel_ids'] or z['channel_ids']==[s['channel_id'] for s in p['series']]) for z,p in zip(flat,y['panels'])))
        xx=copy.deepcopy(x);yy=copy.deepcopy(y)
        for v in [xx,yy]:
            for p in v['panels']:p.pop('insets')
        check('all_unrelated_fields_unchanged',xx==yy)
    arrays=[]
    for key,d in a.datasets.items():
        e=b.datasets.get(key)
        same=e is not None and np.array_equal(d.samples,e.samples) and np.array_equal(d.time_s,e.time_s)
        source_same=e is not None and digest(Path(d.manifest.source_path))==digest(Path(e.manifest.source_path))
        check('data_'+key,same and source_same)
        arrays.append(dict(dataset_id=key,shape=list(d.samples.shape),baseline_matrix_sha256=hashlib.sha256(d.samples.tobytes()).hexdigest(),final_matrix_sha256=hashlib.sha256(e.samples.tobytes()).hexdigest() if e else None,source_sha256=digest(Path(d.manifest.source_path))))
    save_start=time.perf_counter();saved=b.save_project('acceptance_roundtrip');del b
    reopened=load(saved,folder/'fresh_reopen')
    check('save_close_reopen_spec',normalize(reopened.spec)==y)
    check('save_close_reopen_arrays',all(np.array_equal(d.samples,reopened.datasets[k].samples) for k,d in a.datasets.items()))
    save_seconds=time.perf_counter()-save_start
    export_start=time.perf_counter();exports=[];geometry=[];pixel_geometry=[]
    if do_export:
        for lang in ['zh','en']:
            view=reopened.spec.model_copy(update={'languages':reopened.spec.languages.model_copy(update={'axes':lang,'legend':lang})})
            r=render_figure(view,reopened.datasets)
            for p in view.panels:
                for s in p.series:
                    if not s.visible:continue
                    d=next(d for d in reopened.datasets.values() if any(c.channel_id==s.channel_id for c in d.manifest.channels));c=next(c for c in d.manifest.channels if c.channel_id==s.channel_id)
                    factor=conversion_factor(s.unit or c.unit,p.display_unit) if p.display_unit else 1
                    origin=(view.time_axis.event_time_s or 0) if view.time_axis.mode=='relative' else 0
                    np.testing.assert_array_equal(r.lines[(p.id,s.channel_id)].get_xdata(),(d.time_s-origin)*time_factor(view.time_axis.unit))
                    np.testing.assert_array_equal(r.lines[(p.id,s.channel_id)].get_ydata(),d.values(s.channel_id)*factor)
                    main=r.lines[(p.id,s.channel_id)]
                    check(f'main_style_{lang}_{p.id}_{s.channel_id}',(s.color is None or to_rgba(main.get_color())==to_rgba(s.color)) and main.get_linestyle()==s.linestyle and main.get_linewidth()==s.linewidth_pt)
                    for z in p.insets:
                        visible=[q for q in p.series if q.visible and (not z.channel_ids or q.channel_id in z.channel_ids)]
                        if s not in visible:continue
                        line=r.inset_axes[z.id].lines[visible.index(s)];mask=(d.time_s>=z.xlim_s[0])&(d.time_s<=z.xlim_s[1])
                        np.testing.assert_array_equal(line.get_ydata(),d.values(s.channel_id)[mask]*factor)
                        np.testing.assert_array_equal(line.get_xdata(),(d.time_s[mask]-origin)*time_factor(view.time_axis.unit))
                        check(f'inset_inherits_style_{lang}_{z.id}_{s.channel_id}',to_rgba(line.get_color())==to_rgba(main.get_color()) and line.get_linestyle()==main.get_linestyle() and line.get_linewidth()==main.get_linewidth())
                        check(f'inset_exact_series_{lang}_{z.id}',[q.get_gid() for q in r.inset_axes[z.id].lines]==[q.channel_id for q in visible])
                        if z.ylim is None:
                            low,high=r.inset_axes[z.id].get_ylim();visible_values=np.concatenate([line.get_ydata() for line in r.inset_axes[z.id].lines])
                            finite=visible_values[np.isfinite(visible_values)]
                            check(f'inset_auto_y_contains_samples_{lang}_{z.id}',len(finite)>0 and low<float(finite.min()) and high>float(finite.max()))
                geometry.append(dict(language=lang,panel=p.id,title=r.axes[p.id].get_title(),ylabel=r.axes[p.id].get_ylabel(),insets=[z.model_dump(mode='json') for z in p.insets]))
            geom=geometry_checks(r,view,lang);pixel_geometry.append(geom)
            check('geometry_legends_inside_figure_'+lang,all(z['inside_figure'] for z in geom['legends']))
            check('geometry_outside_legends_clear_axes_'+lang,view.legend.location not in ['outside_top','outside_right'] or all(not z['overlaps_main_axes'] for z in geom['legends']))
            check('geometry_titles_labels_ticks_inside_figure_'+lang,all(z['inside_figure'] for z in geom['texts']))
            check('geometry_insets_inside_parent_and_match_bounds_'+lang,all(z['inside_parent'] and z['bounds_match'] for z in geom['insets']))
            for fmt in ['png','pdf','svg']:
                target=folder/f'final_{lang}.{fmt}';export_figure(r,target);exports.append(str(target))
            r.figure.clear()
        check('rendered_main_and_inset_arrays_exact',True)
        check('render_and_export_leave_samples_unchanged',all(np.array_equal(d.samples,reopened.datasets[k].samples) for k,d in a.datasets.items()))
        for p in folder.glob('final_*.pdf'):
            exe=shutil.which('pdftoppm')
            if exe:
                subprocess.run([exe,'-f','1','-singlefile','-scale-to','1500','-png',str(p),str(p.with_name(p.stem+'_pdf'))],check=True,capture_output=True)
            else:
                try:
                    import pypdfium2 as pdfium
                    pdf=pdfium.PdfDocument(p);pdf[0].render(scale=2).to_pil().save(p.with_name(p.stem+'_pdf.png'));pdf.close()
                except ImportError:check('pdf_raster_available',False)
    dump(folder/'initial_figure.json',x);dump(folder/'final_figure.json',y)
    result=dict(task=task,source_project=str(path),checks=checks,passed=all(checks.values()),datasets=arrays,geometry=geometry,pixel_geometry=pixel_geometry,geometry_notice='Programmatic Agg geometry checks do not replace actual PNG and PDF visual inspection',exports=exports,save_reopen_seconds=save_seconds,export_validation_seconds=time.perf_counter()-export_start,total_validation_seconds=time.perf_counter()-started,visual_acceptance='PENDING_ACTUAL_IMAGE_INSPECTION',provenance='Deterministic independent acceptance; not AI task execution; timings excluded from model planning')
    dump(folder/'acceptance.json',result);return result
def main():
    p=argparse.ArgumentParser();p.add_argument('task',choices=['F01','F02','F03']);p.add_argument('project',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--no-export',action='store_true');args=p.parse_args()
    result=validate(args.task,args.project,args.out,not args.no_export)
    print(json.dumps(result,ensure_ascii=True,indent=2,default=lambda value:value.item() if isinstance(value,np.generic) else str(value)));raise SystemExit(0 if result['passed'] else 1)
if __name__=='__main__':main()

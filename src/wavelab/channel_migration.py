"""One-way legacy override migration. Never touches source arrays/files."""
from copy import deepcopy


SERIES_LEGACY = ('label','label_i18n','legend_source','unit','physical_role','confirmation_source')
PANEL_LEGACY = ('ylabel','ylabel_i18n','ylabel_mode','quantity_preset_id','display_unit')


def migrate_attributes(value):
    if not isinstance(value,dict):
        return value
    panels=value.get('panels',())
    legend=value.get('legend')
    if value.get('schema_version','0.4')=='0.4' and panels and all(
        hasattr(p,'series') and not p.display_unit and not p.quantity_preset_id and p.ylabel_mode=='confirmed'
        and not (p.ylabel_i18n.zh or p.ylabel_i18n.en)
        and all(not s.label and not (s.label_i18n.zh or s.label_i18n.en) and not s.unit and s.legend_source=='channel' for s in p.series)
        for p in panels) and not getattr(legend,'show_units',False):
        # Preserve immutable panel/series objects on local reorder operations.
        return value
    data = deepcopy(value)
    # Constructors predating schema_version may pass legacy model objects.
    if 'schema_version' not in data:
        def get(item,key,default=None):
            return item.get(key,default) if isinstance(item,dict) else getattr(item,key,default)
        def text(value):
            if isinstance(value,dict): return any(value.values())
            return bool(getattr(value,'zh','') or getattr(value,'en',''))
        old_fields=get(data.get('legend',{}),'show_units',False) or any(get(p,'display_unit') or get(p,'quantity_preset_id') or get(p,'ylabel_mode','confirmed')!='confirmed' or text(get(p,'ylabel_i18n')) or
            any(get(s,'label') or text(get(s,'label_i18n')) or get(s,'unit') or get(s,'legend_source')=='custom' for s in get(p,'series',[])) for p in data.get('panels',[]))
        if old_fields: data['schema_version']='0.3'
    legacy = data.get('schema_version','0.4') in ('0.2','0.3')
    if not legacy and data.get('schema_version','0.4') != '0.4':
        return data
    data['schema_version']='0.4'
    notes=list(data.get('migration_notes',()))
    # Pydantic callers may pass current immutable model objects.
    def raw(item):
        return {k:getattr(item,k) for k in type(item).model_fields} if hasattr(type(item),'model_fields') else item
    channels={}
    manifests=[]
    for original in data.get('datasets',[]):
        m=dict(raw(original)); rows=[]
        for original_channel in m['channels']:
            c=dict(raw(original_channel))
            q=c.get('quantity')
            if q:
                q=dict(raw(q))
                if legacy and c.get('unit') is None and q.get('unit'):
                    c['unit']=q['unit']
                    notes.append(f"{c['channel_id']}：采用原已确认物理量记录中的源单位 {c['unit']}。")
                if legacy and q.get('unit') and q['unit']!=c.get('unit'):
                    notes.append(f"{c['channel_id']}：旧单位记录冲突，保留通道主单位 {c.get('unit')}；请在表格检查。")
                q.pop('unit',None)
                c['quantity']=q
            rows.append(c); channels[c['channel_id']]=c
        m['channels']=rows; manifests.append(m)
    data['datasets']=manifests
    panels=[]
    for original in data.get('panels',[]):
        p=dict(raw(original)); series=[]
        old_display=p.get('display_unit')
        for original_series in p.get('series',[]):
            s=dict(raw(original_series)); c=channels.get(s['channel_id'])
            old_label=s.get('label_i18n')
            old_label=raw(old_label) if old_label is not None else {}
            labels={v for v in (s.get('label'),*(old_label or {}).values()) if v}
            if legacy and c and any(v!=c['display_name'] for v in labels):
                notes.append(f"{p['id']} / {s['channel_id']}：旧图例 {sorted(labels)} 已统一采用通道名称“{c['display_name']}”。")
            if not legacy and (s.get('label') or any((old_label or {}).values()) or s.get('unit') or s.get('legend_source')=='custom' or s.get('physical_role') or s.get('confirmation_source')):
                raise ValueError('独立曲线名称/单位覆盖已取消，请修改通道属性表。')
            for field in SERIES_LEGACY: s.pop(field,None)
            series.append(s)
        if legacy and any(p.get(k) for k in PANEL_LEGACY):
            notes.append(f"{p['id']}：纵轴标题及显示单位改为自动读取通道属性；未确认信息请在表格检查。")
        if not legacy and (p.get('display_unit') or p.get('quantity_preset_id') or p.get('ylabel_mode','confirmed')!='confirmed' or any(raw(p.get('ylabel_i18n') or {}).values())):
            raise ValueError('独立纵轴物理量/单位覆盖已取消，请修改通道属性表。')
        p['series']=series
        if legacy and old_display:
            # Old explicit Y ranges were measured in old display units.
            from types import SimpleNamespace
            from wavelab.domain.models import Channel
            from wavelab.units import automatic_axis
            from wavelab.quantity_presets import conversion_factor
            views={cid:Channel.model_validate(c) for cid,c in channels.items()}
            panel=SimpleNamespace(plot_mode=p.get('plot_mode','analog'),series=[SimpleNamespace(channel_id=s['channel_id'],visible=s.get('visible',True)) for s in series])
            target=automatic_axis(panel,views)[2]
            if target is None:
                units={views[s.channel_id].unit for s in panel.series if s.visible}
                target=next(iter(units)) if len(units)==1 else None
            try: scale=conversion_factor(old_display,target)
            except ValueError: scale=None
            insets=[dict(raw(i)) for i in p.get('insets',[])]; p['insets']=insets
            for item in [p,*insets]:
                if item.get('ylim') is not None:
                    item['ylim']=[v*scale for v in item['ylim']] if scale is not None else None
            if scale is None:
                notes.append(f"{p['id']}：旧Y范围单位无法可靠换算，恢复自动范围，原采样值不变。")
        for field in PANEL_LEGACY: p.pop(field,None)
        panels.append(p)
    data['panels']=panels
    legend=dict(raw(data.get('legend',{})))
    if not legacy and legend.get('show_units'):
        raise ValueError('图例只读取通道名称，单位统一显示在纵轴。')
    legend.pop('show_units',None); legend.pop('axis_show_units',None); data['legend']=legend
    data['migration_notes']=tuple(dict.fromkeys(notes))
    return data

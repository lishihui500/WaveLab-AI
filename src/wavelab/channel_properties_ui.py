"""Compact source-channel table using real dropdown columns."""
import streamlit as st


UI_VERSION = 3
def apply_channel_table(w, manifest, proposal):
    if not isinstance(proposal,dict) or proposal.get('revision')!=w.revision or proposal.get('binding')!=w.project_epoch:
        raise ValueError('页面已变化，请按当前通道表重新编辑。')
    incoming=proposal.get('rows')
    channels={c.channel_id:c for c in manifest.channels}
    if not isinstance(incoming,list) or len(incoming)!=len(channels) or not all(isinstance(r,dict) and isinstance(r.get('channel_id'),str) for r in incoming) or {r['channel_id'] for r in incoming}!=set(channels):
        raise ValueError('通道身份或行数无效。')
    edits={}
    for row in incoming:
        if set(row)!={'channel_id','display_name','quantity_name','unit'}:
            raise ValueError('只能编辑名称、物理量和单位。')
        c=channels[row['channel_id']]
        values={k:v for k,v in row.items() if k!='channel_id'}
        old=dict(display_name=c.display_name,quantity_name=(c.quantity.preset_id or c.quantity.zh) if c.quantity else '',unit=c.unit)
        if values!=old: edits[c.channel_id]=values
    w.set_channel_properties(edits)


def channel_properties_editor(w, manifest, library, run):
    from pathlib import Path
    import streamlit.components.v1 as components
    from dataclasses import asdict
    component=components.declare_component('wavelab_channel_table',path=str(Path(__file__).with_name('channel_table')))
    with st.expander('通道属性', expanded=True):
        proposal=component(rows=[dict(channel_id=c.channel_id,raw=f'列{c.source_column_index} · {c.raw_header}',
            display_name=c.display_name,quantity_name=(c.quantity.preset_id or c.quantity.zh) if c.quantity else '',unit=c.unit)
            for c in manifest.channels],presets=[asdict(q) for q in library.presets().values()],
            revision=w.revision,binding=w.project_epoch,
            key='channel_table_'+w.project_epoch+manifest.dataset_id+str(w.revision),default=None)
        if proposal:
            nonce=proposal.get('nonce')
            if nonce and nonce!=st.session_state.get('last_channel_table_nonce'):
                st.session_state.last_channel_table_nonce=nonce
                run(apply_channel_table,w,manifest,proposal)

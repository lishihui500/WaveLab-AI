from test_quantity_gui import loaded
from wavelab.local_bridge import execute,status

def test_mcp_change_rerun_undo_updates_single_authority(tmp_path):
    at,w=loaded(tmp_path);cid=w.spec.datasets[0].channels[0].channel_id
    current=status(w,'gui')
    result=execute(w,'gui','apply_plot_actions',dict(expected_project_epoch=current['project_epoch'],expected_revision=current['revision'],expected_fingerprint=current['fingerprint'],
        user_request='源单位 kV',actions=[dict(action='set_channel_properties',channel_id=cid,evidence_quote='源单位 kV',changes=dict(quantity_name='voltage',unit='kV'))]))
    assert result['result']['samples_unchanged']
    at.run();assert not at.exception
    assert w.spec.datasets[0].channels[0].unit=='kV'
    w.undo();at.run();assert w.spec.datasets[0].channels[0].unit is None
    w.redo();at.run();assert w.spec.datasets[0].channels[0].unit=='kV'

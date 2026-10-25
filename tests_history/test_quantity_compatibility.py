"""Legacy JSON and live Pydantic objects are different compatibility boundaries."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest
from pydantic import create_model
from streamlit.testing.v1 import AppTest

from wavelab.domain.models import Metadata, ConfirmedQuantity
from wavelab.quantity_presets import QuantityLibrary
from wavelab.session_runtime import session_workbench
from wavelab.workbench import Workbench

ROOT = Path(__file__).resolve().parents[1]


def legacy_session(tmp_path):
    w = Workbench(tmp_path)
    w.import_bytes(b"Domain,u\n0,25000\n1,26000", "synthetic.csv")
    cid = w.spec.datasets[0].channels[0].channel_id
    w.assign_channels("panel_1", [cid])
    w.confirm_panel_quantity("panel_1", "自定义电压", "My voltage", "V")
    legacy = create_model("ConfirmedQuantity", __base__=Metadata, __module__="wavelab.domain.models",
                          zh=(str,...), en=(str,...), unit=(str,...), confirmation_source=(str,...))
    quantity = legacy(zh="自定义电压", en="My voltage", unit="V", confirmation_source="legacy user confirmation")
    channel = w.spec.datasets[0].channels[0].model_copy(update={"quantity": quantity})
    manifest = w.spec.datasets[0].model_copy(update={"channels": (channel,)})
    w.spec = w.spec.model_copy(update={"datasets": (manifest,)})
    w.saved_spec = w.spec
    w.undo_stack[:] = [w.spec]
    w.redo_stack[:] = [w.spec]
    del w._model_schema_type  # This marker did not exist in the broken release.
    return w


def test_optional_reference_matches_registry_id_without_inferring_from_names(tmp_path):
    q = ConfirmedQuantity.model_validate(dict(zh="电压",en="Voltage",unit="V",confirmation_source="old JSON"))
    assert q.preset_id is None
    assert ConfirmedQuantity.model_validate(q.model_dump()).preset_id is None
    library = QuantityLibrary(tmp_path)
    for identity, preset in library.presets().items():
        assert identity == preset.id
    preset = library.presets()["voltage"]
    chosen = q.model_copy(update={"preset_id":preset.id})
    assert library.presets()[chosen.preset_id].zh == "电压"


def test_old_live_objects_upgrade_with_history_and_samples_intact(tmp_path, monkeypatch):
    w = legacy_session(tmp_path)
    before = w.spec
    assert not hasattr(before.datasets[0].channels[0].quantity, "preset_id")
    arrays = {k:d.samples for k,d in w.data.items()}
    epoch, revision, names = w.project_epoch, w.revision, w.names
    monkeypatch.setattr("wavelab.workbench.parse_file",lambda *a,**k:pytest.fail("migration must not parse"))
    result = session_workbench({"workbench":w},tmp_path)
    assert result is w and w.names is names and w.project_epoch == epoch
    quantity = w.spec.datasets[0].channels[0].quantity
    assert type(quantity) is ConfirmedQuantity
    assert (quantity.preset_id, quantity.zh, quantity.en, quantity.unit) == (None,"自定义电压","My voltage","V")
    assert w.save_status == "已保存"
    assert w.revision == revision + 1
    assert len(w.undo_stack) == len(w.redo_stack) == 1
    assert w.undo_stack[0].datasets[0].channels[0].quantity.preset_id is None
    for key, values in arrays.items():
        assert w.data[key].samples is values and not values.flags.writeable
    migrated, revision = w.spec, w.revision
    assert session_workbench({"workbench":w},tmp_path).spec is migrated
    assert w.revision == revision
    w.undo();w.redo()
    from wavelab.ai.assistant import figure_context
    assert figure_context(w)["datasets"][0]["channels"][0]["quantity"]["preset_id"] is None


def test_legacy_live_session_renders_and_presets_save_reopen(tmp_path):
    w = legacy_session(tmp_path)
    at = AppTest.from_file(ROOT/"app.py",default_timeout=30)
    at.session_state["workbench"] = w
    at.run()
    assert not at.exception
    def select(label): return next(e for e in at.selectbox if e.label == label)
    def click(label): next(e for e in at.button if e.label == label).click().run()
    w.set_channel_properties({w.spec.datasets[0].channels[0].channel_id:dict(quantity_name='voltage',unit='V')})
    at.run();assert not at.exception
    path = w.save_project("legacy_recovered")
    fresh = Workbench(tmp_path/"fresh")
    fresh.open_project(path)
    assert fresh.spec.datasets[0].channels[0].quantity.preset_id == "voltage"
    reopened = AppTest.from_file(ROOT/"app.py",default_timeout=30)
    reopened.session_state["workbench"] = fresh
    reopened.run()
    assert not reopened.exception
    assert reopened.get("component_instance")
    assert fresh.spec.datasets[0].channels[0].unit=="V"


def test_old_project_and_custom_preset_roundtrip(tmp_path):
    w = Workbench(tmp_path)
    w.import_bytes(b"Domain,x\n0,1\n1,2", "synthetic.csv")
    cid = w.spec.datasets[0].channels[0].channel_id
    w.assign_channels("panel_1",[cid])
    w.confirm_panel_quantity("panel_1","用户自定义量","User quantity","arb")
    path = w.save_project("old")
    document = json.loads(path.read_text(encoding="utf-8"))
    for manifest in document["figure"]["datasets"]:
        for channel in manifest["channels"]:
            channel["quantity"].pop("preset_id")
    for panel in document["figure"]["panels"]:
        panel.pop("display_unit",None);panel.pop("quantity_preset_id",None)
    path.write_text(json.dumps(document,ensure_ascii=False),encoding="utf-8")
    w.open_project(path)
    q = w.spec.datasets[0].channels[0].quantity
    assert (q.preset_id,q.zh,q.en,q.unit) == (None,"用户自定义量","User quantity","arb")
    library = QuantityLibrary(w.root)
    identity = library.add_custom("试验量","Test quantity","user_unit")
    w.set_channel_preset(cid,identity,"user_unit")
    saved = w.save_project("custom")
    w.open_project(saved)
    assert w.spec.datasets[0].channels[0].quantity.preset_id == identity
    at = AppTest.from_file(ROOT/"app.py",default_timeout=30)
    at.session_state["workbench"] = w
    at.run()
    assert not at.exception
    assert at.get("component_instance")
    assert w.spec.datasets[0].channels[0].quantity.preset_id==identity


def test_invalid_migration_keeps_the_original_state(tmp_path):
    w = legacy_session(tmp_path)
    invalid = w.spec.panels[0].model_copy(update={"ylim": (2.,1.)})
    w.spec = w.spec.model_copy(update={"panels": (invalid,)})
    before = w.spec
    arrays = {k:d.samples for k,d in w.data.items()}
    with pytest.raises(ValueError):session_workbench({"workbench":w},tmp_path)
    assert w.spec is before
    assert all(w.data[k].samples is values for k,values in arrays.items())


def test_cached_model_modules_refresh_without_dropping_bridge(tmp_path):
    code = r'''
import sys
from pathlib import Path
from pydantic import create_model
import wavelab.domain.models as models
import wavelab.workbench as service
from wavelab.local_bridge import get_bridge
from wavelab.session_runtime import session_workbench
root=Path(sys.argv[1])
w=service.Workbench(root)
w.import_bytes(b"Domain,u\n0,25000\n1,26000", "synthetic.csv")
cid=w.spec.datasets[0].channels[0].channel_id
w.assign_channels("panel_1",[cid])
bridge=get_bridge(root/"runtime")
bridge.attach("test")
port=bridge.server.server_port
samples=next(iter(w.data.values())).samples
models.ConfirmedQuantity=create_model("ConfirmedQuantity",__base__=models.Metadata,
    zh=(str,...),en=(str,...),unit=(str,...),confirmation_source=(str,...))
result=session_workbench({"workbench":w},root)
assert result is w
assert "preset_id" in models.ConfirmedQuantity.model_fields
assert next(iter(w.data.values())).samples is samples
from wavelab.local_bridge import get_bridge as current_bridge
assert current_bridge(root/"runtime") is bridge
assert bridge.server.server_port==port
w.set_channel_preset(cid,"voltage","V")

assert w.spec.datasets[0].channels[0].quantity.preset_id=="voltage"
assert w.spec.schema_version=="0.4"
# Reloading only the leaf module must not leave FigureSpec bound to old manifests.
import importlib
importlib.reload(models)
assert session_workbench({"workbench":w},root) is w
assert next(iter(w.data.values())).samples is samples
assert w.spec.datasets[0].channels[0].quantity.preset_id=="voltage"
assert current_bridge(root/"runtime") is bridge
bridge.close()
'''
    result=subprocess.run([sys.executable,"-c",code,str(tmp_path)],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr


def test_cached_preset_helper_signature_is_refreshed(tmp_path):
    code=r'''
import inspect
import wavelab.quantity_ui as ui
from wavelab.session_runtime import ensure_current_runtime
def legacy_picker(library,prefix,*,current_id=None,on_select=None):
    raise AssertionError("old helper must not run")
ui.preset_picker=legacy_picker
ensure_current_runtime()
assert "current_unit" in inspect.signature(ui.preset_picker).parameters
'''
    result=subprocess.run([sys.executable,"-c",code],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr

"""Regression for Add panel on an already-running pre-order Streamlit server."""
import importlib
from pathlib import Path
import subprocess
import sys

from streamlit.testing.v1 import AppTest
from wavelab.workbench import Workbench
from wavelab.session_runtime import session_workbench

ROOT = Path(__file__).resolve().parents[1]


def old_session(tmp_path):
    w = Workbench(tmp_path)
    w.import_bytes(b"Domain,u,u\n0,1,2\n1,3,4", "synthetic.txt")
    w.assign_channels("panel_1", [c.channel_id for c in w.spec.datasets[0].channels])
    # Same name/module/state as a class that survived Streamlit module replacement.
    legacy = type("Workbench", (), {"__module__": "wavelab.workbench"})
    w.__class__ = legacy
    return w


def test_upgrade_preserves_unsaved_state_and_bindings(tmp_path):
    w = old_session(tmp_path)
    state = {"workbench": w}
    attributes = dict(w.__dict__)
    result = session_workbench(state, tmp_path)
    assert result is w and state["workbench"] is w
    assert w.__dict__.keys() == attributes.keys()
    for name, value in attributes.items():
        assert w.__dict__[name] is value
    samples = next(iter(w.data.values())).samples
    original = w.spec
    w.create_panel("panel_2")
    assert len(w.spec.panels) == 2
    w.undo(); assert w.spec is original
    w.redo(); assert len(w.spec.panels) == 2
    assert next(iter(w.data.values())).samples is samples


def test_cached_old_module_reloaded_and_existing_instance_upgraded(tmp_path):
    # Isolate importlib.reload from other tests' captured class references.
    code = r"""
import wavelab.workbench as service
from wavelab.session_runtime import session_workbench
w=service.Workbench('.')
for name in ('create_panel','move_panel','reorder_panels'):
    delattr(service.Workbench,name)
old_class=type(w)
state={'workbench':w}
result=session_workbench(state,'.')
assert result is w and type(w) is not old_class
assert all(callable(getattr(w,n)) for n in ('create_panel','move_panel','reorder_panels'))
assert session_workbench(state,'.') is w
"""
    result=subprocess.run([sys.executable,"-c",code],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0, result.stderr


def test_add_buttons_on_old_session_and_continuous_insertions(tmp_path):
    w=old_session(tmp_path)
    at=AppTest.from_file(ROOT/"app.py",default_timeout=30)
    at.session_state["workbench"]=w
    at.run(); assert not at.exception
    def button(label):return next(e for e in at.button if e.label==label)
    def select(label):return next(e for e in at.selectbox if e.label==label)
    original=w.spec
    for count in (2,3,4):
        button("添加子图").click().run()
        assert not at.exception
        assert len(w.spec.panels)==count
    select("新子图插入位置").select("在当前子图上方插入").run()
    button("添加子图").click().run()
    assert [p.id for p in w.spec.panels]==["panel_5","panel_1","panel_2","panel_3","panel_4"]
    select("新子图插入位置").select("在当前子图下方插入").run()
    button("添加子图").click().run()
    assert [p.id for p in w.spec.panels]==["panel_5","panel_1","panel_6","panel_2","panel_3","panel_4"]
    assert w.spec.panels[1].series==original.panels[0].series
    button("撤销").click().run()
    assert len(w.spec.panels)==5
    button("恢复").click().run()
    assert len(w.spec.panels)==6
    assert not at.exception


def test_cached_runtime_before_unified_quantity_is_upgraded(tmp_path):
    code = r"""
from pathlib import Path
from streamlit.testing.v1 import AppTest
import wavelab.workbench as service
import wavelab.session_runtime as runtime
w = service.Workbench(Path(__import__('sys').argv[1]))
w.import_bytes(b'Domain,u\n0,1\n1,2', 'synthetic.csv')
w.assign_channels('panel_1', [w.spec.datasets[0].channels[0].channel_id])
spec, samples = w.spec, next(iter(w.data.values())).samples
old_type = type(w)
delattr(service.Workbench, 'configure_panel_quantity')
runtime.RUNTIME_SCHEMA_VERSION = 3
runtime._REQUIRED_API = tuple(n for n in runtime._REQUIRED_API if n != 'configure_panel_quantity')
at = AppTest.from_file('app.py', default_timeout=30)
at.session_state['workbench'] = w
at.run()
assert not at.exception, at.exception
assert at.session_state['workbench'] is w
assert type(w) is not old_type
assert w.spec is spec
assert next(iter(w.data.values())).samples is samples
assert runtime.RUNTIME_SCHEMA_VERSION == 8
assert callable(w.configure_panel_quantity)
def select(label): return next(e for e in at.selectbox if e.label == label)
w.set_channel_properties({w.spec.datasets[0].channels[0].channel_id:dict(quantity_name='inductance',unit='H')})
at.run()
assert not at.exception, at.exception
assert w.spec.datasets[0].channels[0].unit == 'H'
assert w.spec.datasets[0].channels[0].quantity.preset_id == 'inductance'
w.undo()
assert w.spec is spec
assert next(iter(w.data.values())).samples is samples
"""
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], cwd=ROOT,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

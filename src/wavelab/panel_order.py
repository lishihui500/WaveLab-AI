"""Local drag ordering with revision and project binding; no external assets."""
from pathlib import Path
import streamlit.components.v1 as components

_component = components.declare_component("wavelab_panel_order", path=str(Path(__file__).with_name("panel_order_canvas")))


def panel_order(panels, revision, binding):
    return _component(panels=[dict(id=p.id, title=p.title_i18n.zh or p.title_i18n.en) for p in panels], revision=revision, binding=binding, key="panel_order", default=None)


def apply_order_gesture(workbench, gesture):
    if not isinstance(gesture, dict) or type(gesture.get("revision")) is not int or gesture["revision"] != workbench.revision or gesture.get("binding") != workbench.project_epoch:
        raise ValueError("排序来自旧布局，请重新拖动")
    ids = gesture.get("panel_ids")
    if not isinstance(ids, list) or any(not isinstance(pid, str) for pid in ids):
        raise ValueError("非法排序列表")
    workbench.reorder_panels(ids)

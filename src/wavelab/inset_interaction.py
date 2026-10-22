"""Local browser component. Gestures submit once, on pointer release."""
import base64
from pathlib import Path
import streamlit.components.v1 as components

_canvas = components.declare_component("wavelab_inset_canvas", path=str(Path(__file__).with_name("inset_canvas")))


def inset_canvas(image, panels, revision):
    return _canvas(image=base64.b64encode(image).decode("ascii"), panels=panels,
                   revision=revision, key="inset_canvas", default=None)


def apply_gesture(workbench, gesture):
    """Validate browser coordinates against current revision before local commit."""
    from wavelab.domain.figure import ordered_limits
    if not isinstance(gesture, dict) or gesture.get("revision") != workbench.revision:
        raise ValueError("框选或拖动来自旧画布，请重新操作")
    panel = next((p for p in workbench.spec.panels if p.id == gesture.get("panel_id")), None)
    if panel is None:
        raise ValueError("画布子图已失效")
    if gesture.get("kind") == "move":
        inset = next((i for i in panel.insets if i.id == gesture.get("inset_id")), None)
        if inset is None:
            raise ValueError("局部图已失效")
        config = inset.model_dump()
        config["bounds"] = gesture["bounds"]
        workbench.upsert_inset(panel.id, config)
        return None
    if gesture.get("kind") != "select":
        raise ValueError("未知画布操作")
    from wavelab.quantity_presets import time_factor
    factor = time_factor(workbench.spec.time_axis.unit)
    origin = workbench.spec.time_axis.event_time_s or 0
    xlim = ordered_limits(tuple(float(v)/factor+origin for v in gesture["xlim"]))
    ylim = ordered_limits(tuple(float(v) for v in gesture["ylim"]))
    return dict(panel_id=panel.id, xlim_s=xlim, ylim=ylim)

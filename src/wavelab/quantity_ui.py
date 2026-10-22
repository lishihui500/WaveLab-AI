"""Lightweight Streamlit controls, backed by one quantity registry."""
import streamlit as st
from wavelab.quantity_presets import COMMON_UNITS, UNITS


def unit_combo(label, current=None, preset=None, *, key=None, on_change=None):
    if not current and preset:
        current = preset.default_unit
    known = UNITS.get(current)
    candidates = list(preset.units) if preset else (
        [symbol for symbol, unit in UNITS.items() if symbol == unit.symbol and unit.family == known.family]
        if known else list(dict.fromkeys((*COMMON_UNITS, *(unit.symbol for unit in UNITS.values())))))
    if current and current not in candidates:
        candidates.insert(0,current)
    return st.selectbox(label, candidates, index=candidates.index(current) if current else None,
                        accept_new_options=True, placeholder="选择或输入自定义单位", key=key, on_change=on_change)


def preset_picker(library, prefix, *, current_id=None, current_unit=None, on_select=None, sync_scope=None):
    presets = library.presets()
    categories = ["常用","最近使用","全部","电压","电流","功率与能量","控制与频率","电路参数","自定义"]
    common = {"voltage","current","active_power","reactive_power","frequency","time"}
    current = presets.get(current_id)
    default_category = current.category if current and current.id not in common else "常用"
    # A retained widget value otherwise wins over index after MCP, undo, or
    # switching panels. Keep drafts only while editing the same valid state.
    marker = (sync_scope, current_id, current_unit)
    marker_key = prefix + "_binding"
    if st.session_state.get(marker_key) != marker:
        st.session_state[prefix + "_category"] = default_category
        st.session_state[prefix + "_preset"] = (current.id, current_unit or current.default_unit) if current else None
        st.session_state[marker_key] = marker
    category = st.selectbox(prefix + "分类", categories, index=None, key=prefix+"_category")
    if category == "最近使用":
        options = [(r["preset_id"],r["unit"]) for r in library.recent() if r["preset_id"] in presets]
    else:
        options = [(q.id,q.default_unit) for q in presets.values() if category == "全部" or (category == "常用" and q.id in common) or q.category == category]
    if current and current_unit and category != "最近使用":
        options = [(pid,current_unit if pid == current.id else unit) for pid,unit in options]
    selected_index = next((i for i,item in enumerate(options) if item[0] == current_id and (not current_unit or item[1] == current_unit)), None)
    def selected():
        value = st.session_state[prefix+"_preset"]
        if value and on_select:
            if on_select(*value) is False:
                st.session_state[prefix+"_preset"] = next((item for item in options if item[0] == current_id), None)
    selection = st.selectbox(prefix + "物理量预设", options, index=None, on_change=selected if on_select else None,
        format_func=lambda item: presets[item[0]].zh + " / " + presets[item[0]].en + " (" + item[1] + ")",
        placeholder="搜索物理量；保持现有配置直到应用", key=prefix+"_preset")
    return (presets[selection[0]],selection[1]) if selection else (None,None)

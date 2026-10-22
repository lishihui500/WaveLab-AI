"""Display-label checks never infer metadata or convert samples."""
from wavelab.quantity_presets import conversion_factor


def automatic_axis(panel, channels):
    """Derive one axis from channel authority, with real SI scaling only."""
    selected = [channels[s.channel_id] for s in panel.series if s.visible]
    if panel.plot_mode == "digital_tracks":
        return "逻辑状态", "Logic state", None, None
    if not selected or any(c.quantity is None for c in selected):
        return "待确认物理量/单位", "Confirm quantity/unit", None, "请在通道属性表中设置物理量和单位。"
    names = {(c.quantity.zh,c.quantity.en) for c in selected}
    if len(names) != 1:
        return "混合物理量", "Mixed quantities", None, "同一子图包含不同物理量，建议分为不同子图；通道属性已保留。"
    zh,en = next(iter(names))
    units = {c.unit for c in selected}
    if units == {None} and all(c.quantity.preset_id == 'switch_state' for c in selected):
        return zh,en,None,None
    if None in units or '' in units:
        return zh,en,None,"部分通道单位待确认，请在通道属性表中设置。"
    if len(units) == 1:
        return zh,en,next(iter(units)),None
    from wavelab.quantity_presets import QUANTITY_PRESETS
    preset_ids = {c.quantity.preset_id for c in selected}
    preset = QUANTITY_PRESETS.get(next(iter(preset_ids))) if len(preset_ids)==1 else None
    target = preset.default_unit if preset and preset.default_unit in units else sorted(units)[0]
    try:
        for unit in units:
            conversion_factor(unit,target)
    except ValueError:
        return zh,en,None,"同一子图的单位无法直接换算，请分为不同子图；通道属性已保留。"
    return zh,en,target,None


def unit_status(spec, panel):
    channels = {c.channel_id:c for m in spec.datasets for c in m.channels}
    _,_,unit,warning = automatic_axis(panel,channels)
    return ("mixed" if warning else "consistent", warning or "物理量和单位来自通道属性。",unit)


def confirmed_y_axis(spec, panel, language):
    channels = {c.channel_id:c for m in spec.datasets for c in m.channels}
    zh,en,unit,warning = automatic_axis(panel,channels)
    name = en if language == 'en' else zh
    return (f"{name} ({unit})" if unit else name), (f"{panel.id}：{warning}" if warning else None)


def panel_axis_label(spec, panel, language):
    return confirmed_y_axis(spec,panel,language)

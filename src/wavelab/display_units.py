"""Deprecated 0.3 write APIs. 0.4 derives axes from channel attributes."""

def _removed(*args, **kwargs):
    raise ValueError("独立纵轴物理量/显示单位已取消，请使用 set_channel_properties。")

patch_display_unit = _removed
patch_axis_quantity = _removed
patch_panel_quantity = _removed

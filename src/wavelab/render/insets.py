"""Inset range validation and rendering from immutable in-memory samples."""
import numpy as np


def validate_inset(inset, panel, datasets):
    """Shared GUI/command validation; no source or display-unit conversion."""
    if not set(inset.channel_ids) <= {s.channel_id for s in panel.series}:
        raise ValueError("局部图只能选择所属主图的曲线")
    window_data(inset, panel, datasets)
    return inset


def window_data(inset, panel, datasets, *, allow_empty=False):
    channels = {c.channel_id: (d, c) for d in datasets.values() for c in d.manifest.channels}
    selected = set(inset.channel_ids)
    curves = []
    for series in panel.series:
        if not series.visible or (selected and series.channel_id not in selected):
            continue
        dataset, channel = channels[series.channel_id]
        time = dataset.time_s
        # searchsorted preserves duplicate samples and includes both endpoints.
        left = np.searchsorted(time, inset.xlim_s[0], side="left")
        right = np.searchsorted(time, inset.xlim_s[1], side="right")
        if panel.plot_mode == "digital_tracks":
            left = max(0, left - 1)  # carry the held state into the zoom window
        x = time[left:right]
        y = dataset.values(channel.channel_id)[left:right]
        from wavelab.units import automatic_axis
        axis_unit = automatic_axis(panel,{cid:c for cid,(_,c) in channels.items()})[2]
        if axis_unit and channel.unit:
            from wavelab.quantity_presets import conversion_factor
            scale = conversion_factor(channel.unit,axis_unit)
            if scale != 1:
                y = y * scale
        if np.any(np.isfinite(x) & np.isfinite(y)):
            curves.append((series.channel_id, x, y))
    if not curves and not allow_empty:
        raise ValueError(f"Inset {inset.id}: 所选时间窗口没有可见曲线的有效样本")
    return curves


def window_ylim(curves):
    values = [y[np.isfinite(x) & np.isfinite(y)] for _, x, y in curves]
    lo = min(float(v.min()) for v in values)
    hi = max(float(v.max()) for v in values)
    margin = max((hi - lo) * 0.05, abs(lo) * 0.01, abs(hi) * 0.01, 1e-12)
    return lo - margin, hi + margin


def render_insets(panel, parent, lines, datasets, spec, transform, notes):
    axes = {}
    for inset in panel.insets:
        try:
            curves = window_data(inset, panel, datasets)
        except ValueError as exc:
            # A later hide/move can suspend an existing inset; never show stale data.
            notes.append(str(exc))
            continue
        child = parent.inset_axes(inset.bounds, zorder=5)
        child.set_gid(inset.id)
        child.set_in_layout(False)
        for cid, x, y in curves:
            source = lines[(panel.id, cid)]
            # Nonfinite values become gaps only in this derived drawing array.
            plotted_y = np.where(np.isfinite(y), y, np.nan)
            if panel.plot_mode == "digital_tracks":
                from .digital import track_values
                plotted_y = track_values(panel, cid, y)
            line, = child.plot(transform(x, spec), plotted_y, color=source.get_color(),
                              linestyle=source.get_linestyle(), linewidth=source.get_linewidth(),
                              drawstyle=source.get_drawstyle(), label=source.get_label())
            if np.count_nonzero(np.isfinite(plotted_y)) == 1:
                line.set_marker(".")
            line.set_gid(cid)
            line.get_path().should_simplify = False
        child.set_xlim(transform(np.asarray(inset.xlim_s), spec))
        from matplotlib.ticker import ScalarFormatter
        formatter = ScalarFormatter(useOffset=False, useMathText=False)
        formatter.set_scientific(False)
        child.xaxis.set_major_formatter(formatter)
        for event in spec.events:
            if (not event.panel_ids or panel.id in event.panel_ids) and inset.xlim_s[0] <= event.time_s <= inset.xlim_s[1]:
                child.axvline(float(transform(event.time_s, spec)), color=event.color,
                              linestyle=event.linestyle, linewidth=0.65, gid="event_line")
        child.set_ylim(inset.ylim or window_ylim(curves))
        child.tick_params(labelsize=max(6, spec.page.font_size_pt - 2))
        child.locator_params(nbins=3)
        if panel.plot_mode == "digital_tracks":
            from .digital import style_tracks
            style_tracks(child, panel, [lines[(panel.id, s.channel_id)].get_label()
                                      for s in panel.series if s.visible])
            if inset.ylim is not None:
                child.set_ylim(inset.ylim)
        child.grid(False)
        if inset.show_region or inset.show_connectors:
            indicator = parent.indicate_inset_zoom(child, edgecolor="#555555", alpha=0.8)
            # Matplotlib 3.9 returns a tuple; 3.10+ returns InsetIndicator.
            if hasattr(indicator, "rectangle"):
                rectangle, connectors = indicator.rectangle, indicator.connectors
            else:
                rectangle, connectors = indicator
            rectangle.set_clip_on(True)
            rectangle.set_clip_path(parent.patch)
            rectangle.set_visible(inset.show_region)
            for connector in connectors or ():
                connector.set_clip_on(True)
                connector.set_clip_path(parent.patch)
                if not inset.show_connectors:
                    connector.set_visible(False)
        axes[inset.id] = child
    return axes

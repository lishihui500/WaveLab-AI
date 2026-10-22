"""Compact coverage from actual samples; never infer continuity from endpoints."""
from types import SimpleNamespace
import numpy as np
from wavelab.render.insets import window_data


def coverage(w, window_s=None):
    if window_s is not None:
        if len(window_s) != 2 or not np.all(np.isfinite(window_s)) or window_s[0] >= window_s[1]:
            raise ValueError("window_s requires two increasing finite absolute seconds")
    channels = []
    for data in w.datasets.values():
        t = data.time_s
        for c in data.manifest.channels:
            valid = np.isfinite(t) & np.isfinite(data.values(c.channel_id))
            mask = valid if window_s is None else valid & (t >= window_s[0]) & (t <= window_s[1])
            channels.append(dict(channel_id=c.channel_id, start_s=float(t[0]), end_s=float(t[-1]),
                                 point_count=len(t), finite_count=int(valid.sum()),
                                 window_finite_count=int(mask.sum())))
    panels = []
    for panel in w.spec.panels:
        limits = window_s
        if limits is None:
            display = panel.xlim or w.spec.time_axis.xlim
            if display:
                axis = w.spec.time_axis
                origin = axis.event_time_s if axis.mode == "relative" else 0
                scale = {"s": 1, "ms": 1000, "μs": 1000000}[axis.unit]
                limits = [v / scale + (origin or 0) for v in display]
            else:
                limits = [min(d.time_s[0] for d in w.datasets.values()), max(d.time_s[-1] for d in w.datasets.values())]
        curves = window_data(SimpleNamespace(id="coverage", channel_ids=(), xlim_s=limits), panel, w.datasets, allow_empty=True)
        drawable = [cid for cid, _, _ in curves]
        panels.append(dict(panel_id=panel.id, window_s=list(limits), drawable=bool(drawable), channel_ids=drawable))
    return dict(window_s=window_s, channels=channels, panels=panels)

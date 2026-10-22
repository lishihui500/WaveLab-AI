"""Presentation-only binary lanes; source samples and transition times stay intact."""
import numpy as np


def lane_series(panel):
    return [s for s in panel.series if s.visible]


def track_values(panel, channel_id, values):
    values = np.asarray(values)
    if not np.all(np.isfinite(values) & ((values == 0) | (values == 1))):
        raise ValueError(f"Digital track {channel_id}: requires finite binary 0/1 samples")
    index = next(i for i, s in enumerate(lane_series(panel)) if s.channel_id == channel_id)
    # First visible series is the upper lane. Never write into a source view.
    return values + 2 * (len(lane_series(panel)) - 1 - index)


def style_tracks(axis, panel, labels):
    count = len(labels)
    positions, ticks = [], []
    for i, label in enumerate(labels):
        baseline = 2 * (count - 1 - i)
        positions.extend((baseline, baseline + 1))
        ticks.extend((f"{label}  0", "1"))
    axis.set_yticks(positions, ticks)
    axis.set_ylim(-0.25, max(1.25, 2 * count - 0.75))
    axis.grid(False)

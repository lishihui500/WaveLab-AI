"""Headless, deterministic academic drawing; no pyplot global state or LaTeX."""
from dataclasses import dataclass, field
from functools import wraps
from io import BytesIO
import hashlib
import math
from pathlib import Path
import re
import warnings
from threading import RLock

import matplotlib as mpl
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator, ScalarFormatter
import numpy as np

from wavelab.domain import Dataset
from wavelab.domain.figure import FigureSpec
from wavelab.ingest import reopen_file
from wavelab.units import confirmed_y_axis, unit_status, panel_axis_label, automatic_axis
from wavelab.quantity_presets import conversion_factor, time_factor


PALETTE = ("#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#222222")
RENDER_LOCK = RLock()  # rc_context uses process-global Matplotlib settings.


def serialized_render(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with RENDER_LOCK:
            return function(*args, **kwargs)
    return wrapped


@dataclass
class RenderResult:
    figure: Figure
    axes: dict
    lines: dict
    spec: FigureSpec
    warnings: tuple[str, ...]
    font_family: str
    inset_axes: dict = field(default_factory=dict)


def reopen_datasets(spec: FigureSpec, *, base_dir: str | Path = ".") -> dict[str, Dataset]:
    result = {}
    for manifest in spec.datasets:
        if manifest.source_path is None:
            raise ValueError(f"Dataset {manifest.dataset_id} has no source path; bind it explicitly")
        path = Path(manifest.source_path)
        if not path.is_absolute():
            path = Path(base_dir) / path
        result[manifest.dataset_id] = reopen_file(path, manifest)
    return result


def _style(spec, font):
    return {
        "text.usetex": False, "font.family": [font], "font.size": spec.page.font_size_pt,
        "axes.labelsize": spec.page.axes_font_size_pt or spec.page.font_size_pt, "axes.titlesize": spec.page.title_font_size_pt or spec.page.font_size_pt,
        "xtick.labelsize": spec.page.font_size_pt - 1, "ytick.labelsize": spec.page.font_size_pt - 1,
        "legend.fontsize": spec.legend.font_size_pt or max(6, spec.page.font_size_pt - 1),
        "axes.grid": False, "axes.linewidth": 0.65, "axes.unicode_minus": False,
        "xtick.direction": "in", "ytick.direction": "in",
        "xtick.major.width": 0.65, "ytick.major.width": 0.65,
        "path.simplify": False, "agg.path.chunksize": 0,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "path",
        "svg.hashsalt": hashlib.sha256(spec.model_dump_json().encode()).hexdigest(),
        "figure.facecolor": "white", "axes.facecolor": "white",
        "savefig.facecolor": "white", "savefig.transparent": False,
        "mathtext.default": "regular", "mathtext.fontset": "dejavusans",
    }


def _time(values, spec):
    origin = spec.time_axis.event_time_s if spec.time_axis.mode == "relative" else 0
    factor = time_factor(spec.time_axis.unit)
    return (np.asarray(values) - origin) * factor


@serialized_render
def render_figure(spec: FigureSpec, datasets: dict[str, Dataset]) -> RenderResult:
    # Revalidate even if callers used Pydantic model_copy(update=...) to edit.
    spec = FigureSpec.model_validate(spec.model_dump())
    channels = {}
    for manifest in spec.datasets:
        data = datasets.get(manifest.dataset_id)
        if data is None:
            raise ValueError(f"Missing dataset {manifest.dataset_id}")
        expected = manifest.model_dump(exclude={"source_path"})
        if data.manifest.model_dump(exclude={"source_path"}) != expected:
            raise ValueError(f"Dataset {manifest.dataset_id} differs from FigureSpec manifest")
        channels.update({c.channel_id: (data, c) for c in manifest.channels})
    available = {f.name for f in font_manager.fontManager.ttflist}
    font = spec.page.font_family
    notes = []
    if font not in available:
        font = next((f for f in (("Times New Roman", "DejaVu Serif") if spec.languages.axes == "en" else ("SimSun", "Noto Serif CJK SC", "Microsoft YaHei", "DejaVu Sans")) if f in available), "DejaVu Sans")
        notes.append(f"Font {spec.page.font_family} unavailable; using {font}. Verify non-Latin glyphs.")
    legend_font = spec.legend.font_family or ("SimSun" if spec.languages.legend == "zh" else font)
    if legend_font not in available:
        notes.append(f"Legend font {legend_font} unavailable; using {font}.")
        legend_font = font
    # Mixed-language figures must retain CJK glyph coverage without making the
    # English primary font SimSun. Matplotlib selects per-glyph fallbacks.
    cjk = next((f for f in ("SimSun", "Noto Serif CJK SC", "Microsoft YaHei") if f in available), font)
    def label(text, language, fallback):
        if not getattr(text, language) and fallback and (language == "en" or text.zh or text.en):
            notes.append(f"Missing {language} label; fallback: {fallback}")
        return text.resolve(language, fallback)
    n = len(spec.panels)
    columns = spec.legend.columns or (2 if spec.page.width <= 3.5 else 3)
    show_legend = spec.legend.location != "none"
    top_legend = spec.legend.location == "outside_top"
    legend_rows = []
    for panel in spec.panels:
        event_count = sum(not e.panel_ids or panel.id in e.panel_ids for e in spec.events)
        legend_rows.append(math.ceil((sum(s.visible for s in panel.series) + event_count) / columns))
    height = spec.page.height_in or (1.55 * n + 0.55 + sum(legend_rows) * 0.22 if show_legend else 1.55 * n + 0.55)
    axes, lines, inset_axes = {}, {}, {}
    style = _style(spec, font)
    style["font.family"] = list(dict.fromkeys((font, cjk)))
    with mpl.rc_context(style):
        fig = Figure(figsize=(spec.page.width, height), dpi=spec.page.dpi, layout="constrained")
        FigureCanvasAgg(fig)
        fig.get_layout_engine().set(w_pad=0.035, h_pad=0.025, hspace=spec.page.panel_spacing)
        ratios = []
        for rows in legend_rows:
            if top_legend:
                ratios.append(spec.page.legend_spacing * max(1, rows))
            ratios.append(1)
        grid = fig.add_gridspec(len(ratios), 1, height_ratios=ratios)
        first_axis = None
        global_xlim = spec.time_axis.xlim
        if spec.share_time_axis and global_xlim is None:
            global_xlim = next((p.xlim for p in spec.panels if p.xlim is not None), None)
        for i, panel in enumerate(spec.panels):
            row = 2 * i + 1 if top_legend else i
            ax = fig.add_subplot(grid[row], sharex=first_axis if spec.share_time_axis else None)
            if first_axis is None:
                first_axis = ax
            axes[panel.id] = ax
            for j, series in enumerate(panel.series):
                if not series.visible:
                    continue
                dataset, channel = channels[series.channel_id]
                unit = channel.unit
                axis_unit = automatic_axis(panel,{cid:c for cid,(_,c) in channels.items()})[2]
                scale = conversion_factor(unit,axis_unit) if axis_unit and unit else 1.
                curve_label = channel.display_name
                values = dataset.values(series.channel_id)
                plotted = values * scale if scale != 1 else values
                if panel.plot_mode == "digital_tracks":
                    from .digital import track_values
                    plotted = track_values(panel, series.channel_id, values)
                line, = ax.plot(_time(dataset.time_s, spec), plotted,
                                label=curve_label, color=series.color or PALETTE[list(channels).index(series.channel_id) % len(PALETTE)],
                                linestyle=series.linestyle, linewidth=series.linewidth_pt,
                                drawstyle="steps-post" if panel.plot_mode == "digital_tracks" else "default")
                line.set_gid(series.channel_id)
                line.get_path().should_simplify = False
                lines[(panel.id, series.channel_id)] = line
            for event in spec.events:
                if not event.panel_ids or panel.id in event.panel_ids:
                    ax.axvline(float(_time(event.time_s, spec)), label=label(event.label_i18n, spec.languages.legend, event.label),
                               color=event.color, linestyle=event.linestyle, linewidth=0.8,
                               gid="event_line")
            ylabel, confirmation_warning = panel_axis_label(spec, panel, spec.languages.axes)
            ax.set_ylabel(ylabel)
            if confirmation_warning:
                notes.append(confirmation_warning)
            title = label(panel.title_i18n, spec.languages.axes, panel.title)
            if title:
                ax.set_title(title, loc="left", pad=4)
            if panel.ylim is not None:
                ax.set_ylim(panel.ylim)
            limit = global_xlim if spec.share_time_axis else panel.xlim or spec.time_axis.xlim
            if limit is not None:
                ax.set_xlim(limit)
            else:
                ax.margins(x=0)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
            ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
            for which, policy in ((ax.yaxis, panel.scientific_y), (ax.xaxis, "auto")):
                # Plain scientific notation avoids SimSun's missing mathematical minus glyph.
                formatter = ScalarFormatter(useOffset=False, useMathText=False)
                formatter.set_scientific(policy != "never")
                formatter.set_powerlimits((0, 0) if policy == "always" else (-3, 4))
                which.set_major_formatter(formatter)
            if panel.plot_mode == "digital_tracks":
                from .digital import style_tracks
                style_tracks(ax, panel, [lines[(panel.id, s.channel_id)].get_label()
                                        for s in panel.series if s.visible])
            if spec.share_time_axis and i < n - 1:
                ax.tick_params(labelbottom=False)
            else:
                default = (("Relative time" if spec.time_axis.mode == "relative" else "Time") if spec.languages.axes == "en" else ("相对时间" if spec.time_axis.mode == "relative" else "时间")) + f" ({spec.time_axis.unit})"
                ax.set_xlabel(default)
            if show_legend:
                handles, labels = ax.get_legend_handles_labels()
                options = dict(ncols=columns, frameon=False, handlelength=2.3,
                               columnspacing=1.4, borderaxespad=0,
                               prop={"family": list(dict.fromkeys((legend_font, cjk))),
                                     "size": spec.legend.font_size_pt or max(6, spec.page.font_size_pt - 1)})
                if top_legend:
                    legend_ax = fig.add_subplot(grid[row - 1])
                    legend_ax.set_axis_off()
                    legend_ax.legend(handles, labels, loc="center", **options)
                elif spec.legend.location == "outside_right":
                    ax.legend(handles, labels, loc="center left", bbox_to_anchor=(1.02, 0.5), **options)
                else:
                    ax.legend(handles, labels, loc=spec.legend.location, **options)
        from .insets import render_insets
        for panel in spec.panels:
            inset_axes.update(render_insets(panel, axes[panel.id], lines, datasets, spec, _time, notes))
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            fig.canvas.draw()
            fig.canvas.draw()
        # Freeze Agg-calculated geometry; PDF/SVG must not relayout using different font metrics.
        fig.set_layout_engine("none")
        renderer = fig.canvas.get_renderer()
        bounds = fig.bbox
        for axis in fig.axes:
            box = axis.get_tightbbox(renderer)
            if box is not None and (box.x0 < -1 or box.y0 < -1 or box.x1 > bounds.x1 + 1 or box.y1 > bounds.y1 + 1):
                notes.append("Layout: text or legend exceeds page; increase width/height, reduce font size or legend columns.")
                break
        notes.extend(dict.fromkeys(str(w.message) for w in captured))
    return RenderResult(fig, axes, lines, spec, tuple(dict.fromkeys(notes)), font, inset_axes)


@serialized_render
def export_figure(result: RenderResult, path: str | Path):
    target = Path(path).resolve()
    fmt = target.suffix.lower().lstrip(".")
    if fmt not in {"pdf", "png", "svg"}:
        raise ValueError("Supported outputs are PDF, PNG and SVG")
    if any(d.source_path and Path(d.source_path).resolve() == target for d in result.spec.datasets):
        raise ValueError("Cannot overwrite original data")
    target.parent.mkdir(parents=True, exist_ok=True)
    metadata = {"Creator": "WaveLab AI"}
    if fmt == "pdf":
        metadata.update(CreationDate=None, ModDate=None)
    elif fmt == "svg":
        metadata = {"Creator": "WaveLab AI", "Date": None}
    with mpl.rc_context(_style(result.spec, result.font_family)):
        # No tight bbox: retain exact requested physical width, with constrained small margins.
        if fmt == "png" and result.spec.page.dpi < 216:
            # Avoid SimSun's faulty embedded bitmap strikes. Preserve the
            # requested PNG size/DPI by resizing the rendered image only.
            from PIL import Image, PngImagePlugin
            buffer = BytesIO()
            result.figure.savefig(buffer, format="png", dpi=240, metadata=metadata)
            buffer.seek(0)
            with Image.open(buffer) as image:
                size = tuple(int(inches * result.spec.page.dpi) for inches in result.figure.get_size_inches())
                image = image.resize(size, Image.Resampling.LANCZOS)
                info = PngImagePlugin.PngInfo()
                info.add_text("Creator", "WaveLab AI")
                image.save(target, pnginfo=info, dpi=(result.spec.page.dpi, result.spec.page.dpi))
        else:
            result.figure.savefig(target, format=fmt, dpi=result.spec.page.dpi, metadata=metadata)
    if fmt == "svg":
        # Matplotlib hashes unrounded clip bounds; sub-ulp layout differences can
        # change only IDs. Canonicalize generated references, never curve coordinates.
        text = target.read_text(encoding="utf-8")
        generated = list(dict.fromkeys(re.findall(r'id="([pmh][0-9a-f]{10})"', text)))
        for index, identity in enumerate(generated):
            text = text.replace(f'id="{identity}"', f'id="wavelab_{index:04d}"')
            text = text.replace(f'#{identity}', f'#wavelab_{index:04d}')
        target.write_text(text, encoding="utf-8", newline="\n")
    return target

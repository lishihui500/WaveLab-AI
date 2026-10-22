"""Raster preview adapter; uses the unchanged full-sample figure pipeline."""
from io import BytesIO
import matplotlib as mpl

from wavelab.render.engine import render_figure, _style, RENDER_LOCK


PREVIEW_DPI = 240


def preview_png(spec, datasets, *, geometry=False):
    result = render_figure(spec, datasets)
    try:
        output = BytesIO()
        with RENDER_LOCK, mpl.rc_context(_style(result.spec, result.font_family)):
            # SimSun's 12--17 px bitmap strikes render blank on this Windows
            # FreeType build. Minimum 6 pt at 240 dpi uses 20 px outlines.
            result.figure.savefig(output, format="png", dpi=PREVIEW_DPI)
        if geometry:
            panels = []
            for panel in spec.panels:
                axis = result.axes[panel.id]
                box = axis.get_position()
                panels.append(dict(id=panel.id, rect=[box.x0, 1-box.y1, box.width, box.height],
                                   xlim=list(axis.get_xlim()), ylim=list(axis.get_ylim()),
                                   insets=[dict(id=i.id, bounds=list(i.bounds)) for i in panel.insets
                                           if i.id in result.inset_axes]))
            return output.getvalue(), result.warnings, panels
        return output.getvalue(), result.warnings
    finally:
        result.figure.clear()

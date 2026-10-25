import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

import matplotlib as mpl
import numpy as np
from PIL import Image
from pypdf import PdfReader
import pytest

from wavelab.domain.figure import FigureSpec, PageSpec, PanelSpec, SeriesSpec, TimeAxisSpec, load_spec, save_spec
from wavelab.ingest import parse_text
from wavelab.render import export_figure, render_figure, reopen_datasets
from wavelab.render.demos import acceptance_cases

ROOT = Path(__file__).resolve().parents[1]


def verify_exports(result, tmp_path, stem):
    for fmt in ("pdf", "png", "svg"):
        path = export_figure(result, tmp_path / f"{stem}.{fmt}")
        assert path.stat().st_size > 1000
        if fmt == "pdf":
            pdf = PdfReader(path)
            assert len(pdf.pages) == 1
            box = pdf.pages[0].mediabox
            assert float(box.width) == pytest.approx(result.spec.page.width * 72)
            assert float(box.height) == pytest.approx(result.figure.get_size_inches()[1] * 72)
        elif fmt == "png":
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                assert image.width == int(result.spec.page.width * result.spec.page.dpi)
        else:
            svg = ET.parse(path).getroot()
            assert svg.tag.endswith("svg")
            assert len(list(svg.iter())) > 20


@pytest.mark.parametrize("case_index", range(7))
def test_six_real_renderings(case_index, tmp_path):
    name, spec, dataset = acceptance_cases(ROOT)[case_index]
    source = Path(dataset.manifest.source_path)
    original_bytes = source.read_bytes()
    original = dataset.samples.copy()
    # Matplotlib resolves its lazy backend sentinel once; rc_context does not undo that.
    _ = mpl.get_backend()
    rc_before = mpl.rcParams.copy()
    result = render_figure(spec, {dataset.manifest.dataset_id: dataset})
    assert mpl.rcParams == rc_before
    assert result.font_family == "SimSun"  # This Windows acceptance environment has 宋体.
    # Unconfirmed legacy datasets now report metadata requirements; layout/font warnings remain forbidden.
    assert all("物理量" in warning for warning in result.warnings)
    renderer = result.figure.canvas.get_renderer()
    canvas_box = result.figure.bbox
    for ax in result.figure.axes:
        legend = ax.get_legend()
        if legend:
            box = legend.get_window_extent(renderer)
            assert box.x0 >= canvas_box.x0 and box.x1 <= canvas_box.x1
            assert box.y0 >= canvas_box.y0 and box.y1 <= canvas_box.y1
            assert all(not box.overlaps(plot_ax.bbox) for plot_ax in result.axes.values())
    origin = spec.time_axis.event_time_s if spec.time_axis.mode == "relative" else 0
    factor = 1000 if spec.time_axis.unit == "ms" else 1
    expected_x = (dataset.time_s - origin) * factor
    for panel in spec.panels:
        assert not any(line.get_visible() for line in result.axes[panel.id].get_xgridlines())
        for series in panel.series:
            line = result.lines[(panel.id, series.channel_id)]
            assert line.get_gid() == series.channel_id
            np.testing.assert_array_equal(line.get_xdata(), expected_x)
            np.testing.assert_array_equal(line.get_ydata(), dataset.values(series.channel_id))
            assert len(line.get_xdata()) == len(dataset.samples)
            assert line.get_path().should_simplify is False
    initial_pixels = np.asarray(result.figure.canvas.buffer_rgba()).copy()
    path = tmp_path / f"{name}.json"
    save_spec(spec, path)
    persisted = load_spec(path)
    replay = render_figure(persisted, reopen_datasets(persisted, base_dir=tmp_path))
    np.testing.assert_array_equal(initial_pixels, replay.figure.canvas.buffer_rgba())
    verify_exports(result, tmp_path, name)
    np.testing.assert_array_equal(dataset.samples, original)
    assert source.read_bytes() == original_bytes
    if case_index == 0:
        event_lines = [l for l in result.axes["currents"].lines if l.get_gid() == "event_line"]
        assert len(event_lines) == 1
        assert event_lines[0].get_xdata() == [0, 0]
    if case_index == 1:
        assert spec.events == ()
    if case_index == 2:
        assert [c.physical_role for c in dataset.manifest.channels] == ["A相上桥臂", "A相下桥臂", "B相上桥臂", "B相下桥臂", "C相上桥臂", "C相下桥臂"]
    if case_index == 3:
        assert len(dataset.samples) == 100002
        assert all(c.physical_role is None for c in dataset.manifest.channels)
    result.figure.clear()
    replay.figure.clear()


def synthetic_spec(time, **kwargs):
    data = parse_text("Domain,u,u\n0,1e-7,1e7\n0.001,2e-7,2e7\n0.004,3e-7,1e7", dataset_id="s")
    spec = FigureSpec(datasets=(data.manifest,), time_axis=time,
                      panels=(PanelSpec(id="tiny", scientific_y="always", series=(SeriesSpec(channel_id="s:col_1"),)),
                              PanelSpec(id="huge", series=(SeriesSpec(channel_id="s:col_2"),))), **kwargs)
    return data, spec


@pytest.mark.parametrize("mode,unit,origin", [("absolute", "s", None), ("absolute", "ms", None), ("relative", "s", 0.001), ("relative", "ms", 0.001)])
def test_time_display_and_multiple_scales(mode, unit, origin):
    data, spec = synthetic_spec(TimeAxisSpec(mode=mode, unit=unit, event_time_s=origin))
    before = data.samples.copy()
    result = render_figure(spec, {"s": data})
    expected = (data.time_s - (origin or 0)) * (1000 if unit == "ms" else 1)
    for line in result.lines.values():
        np.testing.assert_array_equal(line.get_xdata(), expected)
    assert result.axes["tiny"].get_shared_x_axes().joined(result.axes["tiny"], result.axes["huge"])
    assert result.axes["tiny"].get_ylim()[1] < 1e-6
    assert result.axes["huge"].get_ylim()[1] > 1e7
    np.testing.assert_array_equal(data.samples, before)


def test_multiple_datasets_and_display_name_independence(tmp_path):
    a = parse_text("Domain,x\n0,1\n1,2", dataset_id="a")
    b = parse_text("Domain,x\n0,3\n1,4", dataset_id="b")
    spec = FigureSpec(datasets=(a.manifest, b.manifest), panels=(PanelSpec(id="p", series=(SeriesSpec(channel_id="a:col_1", label="same"), SeriesSpec(channel_id="b:col_1", label="same"))),))
    result = render_figure(spec, {"a": a, "b": b})
    np.testing.assert_array_equal(result.lines[("p", "a:col_1")].get_ydata(), [1, 2])
    np.testing.assert_array_equal(result.lines[("p", "b:col_1")].get_ydata(), [3, 4])
    with pytest.raises(ValueError, match="Missing dataset"):
        render_figure(spec, {"a": a})
    with pytest.raises(ValueError, match="differs"):
        render_figure(spec, {"a": b, "b": b})
    with pytest.raises(ValueError, match="no source path"):
        reopen_datasets(spec)
    with pytest.raises(ValueError, match="outputs"):
        export_figure(result, tmp_path / "original.txt")
    assert not (tmp_path / "original.txt").exists()


def test_font_fallback_and_no_latex():
    data, spec = synthetic_spec(TimeAxisSpec(), page=PageSpec(font_family="Missing test font"))
    result = render_figure(spec, {"s": data})
    assert "unavailable" in result.warnings[0]
    assert all(not artist.get_usetex() for ax in result.axes.values() for artist in (ax.xaxis.label, ax.yaxis.label))


def test_deterministic_export_bytes(tmp_path):
    data, spec = synthetic_spec(TimeAxisSpec(), page=PageSpec(font_family="DejaVu Sans"))
    # ASCII text avoids reliance on Chinese fonts in this synthetic test.
    payload = spec.model_dump()
    payload["time_axis"]["label"] = "Time (s)"
    for panel in payload["panels"]:
        panel["ylabel"] = "Value"
    spec = FigureSpec.model_validate(payload)
    a = render_figure(spec, {"s": data})
    b = render_figure(load_spec_roundtrip(spec), {"s": data})
    for fmt in ("pdf", "png", "svg"):
        pa = export_figure(a, tmp_path / f"a.{fmt}")
        pb = export_figure(b, tmp_path / f"b.{fmt}")
        assert hashlib.sha256(pa.read_bytes()).digest() == hashlib.sha256(pb.read_bytes()).digest()


def load_spec_roundtrip(spec):
    return FigureSpec.model_validate_json(spec.model_dump_json())


def test_render_cli_reopens_relative_source(tmp_path, monkeypatch, capsys):
    from wavelab.ingest import parse_file
    from wavelab.render.cli import main
    source = tmp_path / "input.csv"
    source.write_text("Domain,u\n0,1\n1,2", encoding="utf-8")
    original = source.read_bytes()
    data = parse_file(source, dataset_id="cli")
    manifest = data.manifest.model_dump()
    manifest["source_path"] = "input.csv"
    spec = FigureSpec(datasets=(manifest,), panels=(PanelSpec(id="p", series=(SeriesSpec(channel_id="cli:col_1"),)),))
    path = tmp_path / "figure.json"
    save_spec(spec, path)
    out = tmp_path / "export"
    monkeypatch.setattr("sys.argv", ["wavelab-render", str(path), "--output-dir", str(out)])
    assert main() == 0
    assert len(list(out.iterdir())) == 3
    assert ".pdf" in capsys.readouterr().out
    assert source.read_bytes() == original
    monkeypatch.setattr("sys.argv", ["wavelab-render", str(tmp_path / "missing.json"), "--output-dir", str(out)])
    assert main() == 1
    assert capsys.readouterr().err

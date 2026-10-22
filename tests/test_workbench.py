import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from pypdf import PdfReader

from wavelab.domain.figure import FigureSpec, PanelSpec
from wavelab.render.engine import render_figure
from wavelab.workbench import Workbench, safe_name


RAW = b"Domain,u,u\n0,1,2\n0.001,3,4\n0.002,5,6\n"
ROOT = Path(__file__).resolve().parents[1]


def setup(tmp_path):
    w = Workbench(tmp_path)
    identity = w.import_bytes(RAW, "paste.txt")
    ids = [c.channel_id for c in w.spec.datasets[0].channels]
    w.assign_channels("panel_1", ids)
    return w, identity, ids


def test_atomic_update_undo_redo_identity(tmp_path):
    w, identity, ids = setup(tmp_path)
    original = w.spec
    with pytest.raises(ValueError):
        w.update(["panels", 0, "ylim"], [5, 1])
    assert w.spec == original
    w.set_channel_properties({ids[0]:dict(display_name="上桥臂")})
    labels = w.spec
    w.update(["panels", 0, "series", 0, "color"], "red")
    w.undo()
    assert w.spec == labels
    w.redo()
    assert w.spec.panels[0].series[0].color == "red"
    w.edit_channels(identity, {ids[0]: dict(display_name="改名", unit="kA")})
    assert w.spec.datasets[0].channels[0].channel_id == ids[0]
    assert w.datasets[identity].manifest == w.spec.datasets[0]
    w.undo()
    assert w.datasets[identity].manifest.channels[0].display_name == "上桥臂"
    np.testing.assert_array_equal(w.data[identity].samples[:, 1], [1, 3, 5])
    assert not w.datasets[identity].samples.flags.writeable
    with pytest.raises(ValueError):
        w.update(["execute_python"], "print('bad')")
    payload = w.spec.model_dump(mode="json")
    payload["datasets"][0]["source_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        w.commit(payload)


def test_save_close_reopen_paste_and_corruption(tmp_path):
    w, identity, ids = setup(tmp_path / "first")
    w.set_channel_properties({ids[0]:dict(display_name="电流")})
    path = w.save_project("粘贴数据工程")
    stored = json.loads(path.read_text(encoding="utf-8"))
    copied = path.parent / stored["figure"]["datasets"][0]["source_path"]
    assert copied.read_bytes() == RAW
    # Saved project must not need the import/session store.
    Path(w.spec.datasets[0].source_path).unlink()
    restored = Workbench(tmp_path / "second")
    restored.open_project(path)
    assert restored.spec.panels == w.spec.panels
    assert restored.spec.datasets[0].dataset_id == identity
    np.testing.assert_array_equal(restored.datasets[identity].samples, w.datasets[identity].samples)
    restored.update(["panels", 0, "ylim"], [0, 10])
    restored.save_project("继续编辑")
    good = restored.spec
    copied.write_bytes(RAW.replace(b"1,2", b"8,9"))
    with pytest.raises(ValueError, match="SHA-256"):
        restored.open_project(path)
    assert restored.spec == good


def test_old_v02_and_unknown_schema(tmp_path):
    w, _, _ = setup(tmp_path)
    payload = w.spec.model_dump(mode="json")
    payload["schema_version"] = "0.2"
    payload.pop("languages")
    for panel in payload["panels"]:
        panel.pop("title_i18n")
        panel.pop("ylabel_i18n",None)
        for s in panel["series"]:
            s.pop("label_i18n",None)
    old = FigureSpec.model_validate(payload)
    assert old.schema_version == "0.4"
    assert old.panels[0].series[0].channel_id == w.spec.panels[0].series[0].channel_id
    w.open_spec(json.dumps(payload))
    assert w.spec == old
    payload["schema_version"] = "9.0"
    with pytest.raises(ValueError):
        FigureSpec.model_validate(payload)


def test_bilingual_mixed_views_and_exports(tmp_path):
    w, identity, ids = setup(tmp_path)
    w.set_channel_properties({ids[0]:dict(display_name="电流")})
    w.confirm_panel_quantity("panel_1", "电流", "Current", "kA")
    w.update(["languages"], dict(legend="zh", axes="en"))
    original = w.spec
    result = render_figure(w.spec, w.datasets)
    assert result.lines[("panel_1", ids[0])].get_label() == "电流"
    assert result.axes["panel_1"].get_ylabel() == "Current (kA)"
    paths, notes = w.export("图", bilingual=True)
    assert len(paths) == 6
    assert w.spec == original
    assert {p.suffix for p in paths} == {".pdf", ".svg", ".png"}
    for p in paths:
        assert p.stat().st_size > 1000
        if p.suffix == ".pdf":
            assert float(PdfReader(p).pages[0].mediabox.width) == pytest.approx(7.16 * 72)
    w.preset("en", "ieee_single_column")
    assert w.spec.page.font_family == "Times New Roman"
    assert w.spec.panels == original.panels


def test_curve_move_hide_remove_and_event(tmp_path):
    w, _, ids = setup(tmp_path)
    w.update(["panels"], [p.model_dump() for p in w.spec.panels] + [PanelSpec(id="p2").model_dump()])
    w.move_series("panel_1", ids[0], "p2")
    w.update(["panels", 1, "series", 0, "visible"], False)
    result = render_figure(w.spec, w.datasets)
    assert len(result.lines) == 1
    w.update(["events"], [dict(time_s=0.001, label="Event", label_i18n=dict(zh="事件", en="Event"), confirmation_source="test user")])
    w.update(["time_axis"], dict(mode="relative", unit="ms", event_time_s=0.001, xlim=[-1, 1]))
    result = render_figure(w.spec, w.datasets)
    np.testing.assert_array_equal(next(iter(result.lines.values())).get_xdata(), [-1, 0, 1])
    assert result.axes["panel_1"].lines[-1].get_xdata() == [0., 0.]
    w.assign_channels("panel_1", [])
    assert not w.spec.panels[0].series


@pytest.mark.parametrize("name", ["../bad", "CON", "test/escape", "a.", ""])
def test_unsafe_names(name):
    with pytest.raises(ValueError):
        safe_name(name)


@pytest.mark.parametrize("path", sorted((ROOT / "test" / "fixtures").glob("*.txt")), ids=lambda p: p.name)
def test_six_real_import_service(tmp_path, path):
    from wavelab.ingest import parse_file
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    w = Workbench(tmp_path)
    identity = w.import_bytes(raw, path.name)
    reference = parse_file(path)
    np.testing.assert_array_equal(w.data[identity].samples, reference.samples)
    assert w.spec.datasets[0].raw_headers == reference.manifest.raw_headers
    saved = w.save_project("真实数据")
    w2 = Workbench(tmp_path / "new")
    w2.open_project(saved)
    np.testing.assert_array_equal(w2.data[identity].samples, reference.samples)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_mapping_confirmed_and_persisted(tmp_path):
    w = Workbench(tmp_path)
    path = ROOT / "test" / "fixtures" / "测试集1.txt"
    identity = w.import_bytes(path.read_bytes(), path.name)
    with pytest.raises(ValueError):
        w.map_channels(identity, "Udc_cap_SC", "six_arms", "")
    w.map_channels(identity, "Udc_cap_SC", "six_arms", "需求确认顺序", "kV")
    save = w.save_project("六桥臂")
    other = Workbench(tmp_path / "new")
    other.open_project(save)
    assert [c.physical_role for c in other.spec.datasets[0].channels] == ["A相上桥臂", "A相下桥臂", "B相上桥臂", "B相下桥臂", "C相上桥臂", "C相下桥臂"]


@pytest.mark.parametrize("location", ["outside_top", "outside_right", "upper right", "upper left", "lower right", "lower left", "none"])
def test_legend_layout_options(tmp_path, location):
    w, _, ids = setup(tmp_path)
    w.update(["legend", "location"], location)
    w.update(["legend", "columns"], 1)
    w.set_channel_properties({ids[0]:dict(display_name="A相上桥臂电流")})
    w.set_languages("en", "en")
    result = render_figure(w.spec, w.datasets)
    assert result.lines[("panel_1", ids[0])].get_label() == "A相上桥臂电流"
    assert not any("Layout:" in note for note in result.warnings)
    legends = [a.get_legend() for a in result.figure.axes if a.get_legend()]
    assert bool(legends) == (location != "none")
    if location.startswith("outside"):
        renderer = result.figure.canvas.get_renderer()
        assert all(not lg.get_window_extent(renderer).overlaps(ax.bbox) for lg in legends for ax in result.axes.values())


def test_multiple_datasets_and_manifest_import(tmp_path):
    w, first, ids = setup(tmp_path)
    second = w.import_bytes(RAW, "same content.txt")
    assert first != second
    ids2 = [c.channel_id for c in w.spec.datasets[1].channels]
    w.assign_channels("panel_1", [*ids, *ids2])
    path = w.save_project("多数据集")
    restored = Workbench(tmp_path / "fresh")
    restored.open_project(path)
    assert len(restored.spec.datasets) == 2
    assert restored.spec.panels == w.spec.panels
    assert len(render_figure(restored.spec, restored.datasets).lines) == 4


def test_project_rejects_path_escape_without_changing_session(tmp_path):
    w, _, _ = setup(tmp_path)
    p = w.save_project("safe")
    document = json.loads(p.read_text(encoding="utf-8"))
    document["figure"]["datasets"][0]["source_path"] = "../../../source.txt"
    p.write_text(json.dumps(document), encoding="utf-8")
    previous = w.spec
    with pytest.raises(ValueError, match="data"):
        w.open_project(p)
    assert w.spec == previous


def test_parallel_render_context_isolation(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import matplotlib as mpl
    w, _, _ = setup(tmp_path)
    specs = []
    for language in ("zh", "en"):
        w.set_languages(language, language)
        specs.append(w.spec)
    _ = mpl.get_backend()
    before = mpl.rcParams.copy()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda s: render_figure(s, w.datasets), specs))
    assert [r.font_family for r in results] == ["SimSun", "Times New Roman"]
    assert mpl.rcParams == before

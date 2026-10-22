import pytest
from pydantic import ValidationError

from wavelab.domain.figure import EventSpec, FigureSpec, PageSpec, PanelSpec, SeriesSpec, TimeAxisSpec, load_spec, save_spec
from wavelab.ingest import parse_text


def minimal():
    data = parse_text("Domain,u,u\n0,1,2\n1,3,4", dataset_id="synthetic")
    spec = FigureSpec(datasets=(data.manifest,), panels=(PanelSpec(id="p1", series=(SeriesSpec(channel_id="synthetic:col_1"),)),))
    return data, spec


def test_json_roundtrip(tmp_path):
    data, spec = minimal()
    path = tmp_path / "figure.json"
    save_spec(spec, path)
    loaded = load_spec(path)
    assert loaded == spec
    assert loaded.model_dump_json() == spec.model_dump_json()
    assert "samples" not in loaded.model_dump()
    assert data.samples.shape == (2, 3)


@pytest.mark.parametrize("edit", [
    {"time_axis": {"mode": "relative"}},
    {"time_axis": {"unit": "minutes"}},
    {"time_axis": {"event_time_s": 0}},
    {"time_axis": {"xlim": [1, 1]}},
    {"time_axis": {"xlim": [1, 0]}},
    {"time_axis": {"xlim": [0, float("inf")]}},
    {"page": {"dpi": 0}},
    {"page": {"preset": "custom"}},
    {"page": {"width_in": 5}},
    {"page": {"height_in": float("nan")}},
    {"execute_python": "import os"},
    {"panels": []},
    {"legend": {"location": "best"}},
    {"events": [{"time_s": 0, "label": "fault", "confirmation_source": " "}]},
    {"events": [{"time_s": 0, "label": "fault", "confirmation_source": "user", "panel_ids": ["unknown"]}]},
    {"events": [{"time_s": float("nan"), "label": "fault", "confirmation_source": "user"}]},
])
def test_bad_schema(edit):
    _, spec = minimal()
    payload = spec.model_dump()
    payload.update(edit)
    with pytest.raises(ValidationError):
        FigureSpec.model_validate(payload)


@pytest.mark.parametrize("series_edit", [
    {"channel_id": "synthetic:col_3"}, {"channel_id": "u"}, {"channel_id": "synthetic:col_0"},
    {"color": "bad_color"}, {"linewidth_pt": 0}, {"linestyle": "random"},
    {"physical_role": "A相"}, {"smooth": True},
])
def test_bad_series(series_edit):
    _, spec = minimal()
    payload = spec.model_dump()
    payload["panels"][0]["series"][0].update(series_edit)
    with pytest.raises(ValidationError):
        FigureSpec.model_validate(payload)


@pytest.mark.parametrize("problem", ["panel_ids", "dataset_ids", "series_ids", "shared_xlim", "mixed_units", "ylim"])
def test_reference_and_axis_errors(problem):
    _, spec = minimal()
    payload = spec.model_dump()
    if problem == "panel_ids":
        payload["panels"] *= 2
    elif problem == "dataset_ids":
        payload["datasets"] *= 2
    elif problem == "series_ids":
        payload["panels"][0]["series"] *= 2
    elif problem == "shared_xlim":
        payload["time_axis"]["xlim"] = [0, 1]
        payload["panels"][0]["xlim"] = [1, 2]
    elif problem == "ylim":
        payload["panels"][0]["ylim"] = [1, 0]
    else:
        payload["panels"][0]["series"] = [dict(channel_id="synthetic:col_1", unit="kA"), dict(channel_id="synthetic:col_2", unit="kV")]
    with pytest.raises(ValidationError):
        FigureSpec.model_validate(payload)


def test_unshared_xlim_valid():
    _, spec = minimal()
    payload = spec.model_dump()
    payload["share_time_axis"] = False
    payload["time_axis"]["xlim"] = [0, 1]
    payload["panels"][0]["xlim"] = [1, 2]
    FigureSpec.model_validate(payload)


def test_save_rejects_txt(tmp_path):
    _, spec = minimal()
    with pytest.raises(ValueError, match=".json"):
        save_spec(spec, tmp_path / "original.txt")
    assert not (tmp_path / "original.txt").exists()


def test_confirmed_unit_conflict_rejected():
    from wavelab.domain.mapping import map_group
    data, spec = minimal()
    mapped = map_group(data.manifest, "u", "numbered", unit="kV", confirmation_source="User confirmed voltage")
    payload = spec.model_dump()
    payload["datasets"] = [mapped.model_dump()]
    payload["panels"][0]["series"][0]["unit"] = "kA"
    with pytest.raises(ValidationError, match="独立曲线"):
        FigureSpec.model_validate(payload)

import json

import numpy as np
import pytest
from pydantic import ValidationError

from wavelab.domain import DatasetManifest
from wavelab.domain.mapping import map_group
from wavelab.ingest import ParseError, parse_file, parse_text, reopen_file


@pytest.mark.parametrize("suffix", ["txt", "csv"])
@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "gb18030"])
def test_file_encoding_and_newlines(tmp_path, suffix, encoding):
    path = tmp_path / f"中文.{suffix}"
    path.write_bytes('Domain, 电流, 电流\r\n0,1e-3,-2E+2\r\n0.01,3,4\r\n'.encode(encoding))
    dataset = parse_file(path)
    assert dataset.manifest.raw_headers == ("Domain", " 电流", " 电流")
    assert dataset.samples.tolist() == [[0, 0.001, -200], [0.01, 3, 4]]
    assert dataset.manifest.encoding == encoding
    assert [w.code for w in dataset.manifest.warnings] == (["encoding_fallback"] if encoding == "gb18030" else [])


def test_interleaved_repeated_headers():
    dataset = parse_text('Domain, a,b, a,b\n0,1,2,3,4\n1,5,6,7,8\n', dataset_id="test_001")
    assert dataset.manifest.raw_headers == ("Domain", " a", "b", " a", "b")
    assert [c.group_index for c in dataset.manifest.channels] == [0, 0, 1, 1]
    assert [g.channel_ids for g in dataset.manifest.groups] == [("test_001:col_1", "test_001:col_3"), ("test_001:col_2", "test_001:col_4")]
    np.testing.assert_array_equal(dataset.values("test_001:col_3"), [3, 7])
    with pytest.raises(KeyError):
        dataset.values("a")


def test_identity_survives_rename_and_is_distinct_between_imports():
    a = parse_text("Domain,x\n0,1\n1,1")
    b = parse_text("Domain,x\n0,1\n1,1")
    assert a.manifest.channels[0].channel_id != b.manifest.channels[0].channel_id
    payload = a.manifest.model_dump()
    payload["channels"][0]["display_name"] = "任意展示名称"
    renamed = DatasetManifest.model_validate(payload)
    assert renamed.channels[0].channel_id == a.manifest.channels[0].channel_id


@pytest.mark.parametrize("tail,lines", [("\n", (4,)), (", \n\n,\n", (4, 5, 6))])
def test_only_empty_tail_removed(tail, lines):
    dataset = parse_text("Domain,x\n0,7\n1,7\n" + tail)
    assert dataset.samples.tolist() == [[0, 7], [1, 7]]
    assert dataset.manifest.warnings[0].line_numbers == lines


@pytest.mark.parametrize("text,code,line,column", [
    ("", "empty_file", None, None),
    ("t,x\n0,1", "header", 1, None),
    ("Domain\n0", "header", 1, None),
    ("Domain, \n0,1", "header", 1, None),
    ("Domain,x\n,\n", "no_samples", None, None),
    ("Domain,x\n0,1\n1", "row_width", 3, None),
    ("Domain,x\n0,1\n1,2,3", "row_width", 3, None),
    ("Domain,x\n0,1\n1, ", "missing_value", 3, 1),
    ("Domain,x\n0,1\n,2", "missing_value", 3, 0),
    ("Domain,x\n0,1\n1,foo", "not_numeric", 3, 1),
    ("Domain,x\n0,1\n1,NaN", "nonfinite", 3, 1),
    ("Domain,x\n0,1\n1,-Inf", "nonfinite", 3, 1),
    ("Domain,x\n0,1\n1,1e999", "nonfinite", 3, 1),
    ("Domain,x\n0,1\nInf,2", "nonfinite", 3, 0),
    ("Domain,x\n0,1\n0,1", "duplicate_time", 3, 0),
    ("Domain,x\n1,1\n0,2", "reversed_time", 3, 0),
    ("Domain,x\n0,1\n, \n1,2", "interior_empty_row", 3, None),
    ('Domain,x\n0,"1', "csv_syntax", 2, None),
])
def test_reject_invalid_without_dropping_samples(text, code, line, column):
    with pytest.raises(ParseError) as caught:
        parse_text(text)
    assert (caught.value.code, caught.value.line_number, caught.value.source_column_index) == (code, line, column)


def test_nonuniform_samples_are_retained():
    data = parse_text("Domain,x\n0,1\n0.01,2\n0.03,3")
    assert data.manifest.sampling.uniform is False
    assert data.manifest.sampling.sampling_rate_hz is None
    assert data.manifest.sampling.dt_min_s == 0.01
    assert data.manifest.sampling.dt_max_s == pytest.approx(0.02)
    assert data.manifest.warnings[0].code == "nonuniform_sampling"
    np.testing.assert_array_equal(data.samples, [[0, 1], [0.01, 2], [0.03, 3]])


def test_one_sample_and_different_sampling_rate():
    single = parse_text("Domain,x\n0,1")
    assert single.manifest.sampling.uniform is None
    assert single.manifest.sampling.dt_median_s is None
    assert single.manifest.warnings[0].code == "single_sample"
    regular = parse_text("Domain,x\n-1,1\n-0.5,2\n0,3")
    assert regular.manifest.sampling.sampling_rate_hz == 2


def test_array_is_readonly_including_views():
    data = parse_text("Domain,x\n0,1\n1,2")
    with pytest.raises(ValueError):
        data.samples[0, 1] = 10
    with pytest.raises(ValueError):
        data.samples.setflags(write=True)
    with pytest.raises(ValueError):
        data.time_s.setflags(write=True)
    with pytest.raises(ValidationError):
        data.manifest.dataset_id = "changed"


def test_changed_source_rejected(tmp_path):
    source = tmp_path / "synthetic.csv"
    source.write_text("Domain,x\n0,1\n1,2", encoding="utf-8")
    original = parse_file(source)
    source.write_text("Domain,x\n0,1\n1,3", encoding="utf-8")
    with pytest.raises(ParseError, match="source_changed"):
        reopen_file(source, original.manifest)


@pytest.mark.parametrize("field,value", [("channel_id", "wrong"), ("source_column_index", 2), ("raw_header", "wrong"), ("group_index", 2)])
def test_invalid_manifest_identity_rejected(field, value):
    data = parse_text("Domain,x\n0,1\n1,2").manifest.model_dump()
    data["channels"][0][field] = value
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(data)


def test_mapping_requires_confirmation_and_correct_width():
    data = parse_text("Domain,u,u,u,v\n0,1,2,3,4\n1,2,3,4,5")
    assert all(c.physical_role is None for c in data.manifest.channels)
    with pytest.raises(ValueError, match="confirmation"):
        map_group(data.manifest, "u", "ABC", confirmation_source=" ")
    with pytest.raises(ValueError, match="count"):
        map_group(data.manifest, "u", "six_arms", confirmation_source="test")
    with pytest.raises(KeyError):
        map_group(data.manifest, "missing", "ABC", confirmation_source="test")
    with pytest.raises(ValueError, match="Unknown"):
        map_group(data.manifest, "u", "other", confirmation_source="test")
    mapped = map_group(data.manifest, "u", "ABC", confirmation_source="User confirmed synthetic ABC", unit="kV")
    assert [c.physical_role for c in mapped.channels] == ["A相", "B相", "C相", None]
    assert mapped.channels[-1] == data.manifest.channels[-1]
    numbered = map_group(mapped, "u", "numbered", confirmation_source="User selects numbers")
    assert all(c.physical_role is None for c in numbered.channels)


def test_cli_reports_success_and_error(tmp_path, monkeypatch, capsys):
    from wavelab.cli import main
    path = tmp_path / "synthetic.csv"
    path.write_text("Domain,x\n0,1\n1,2", encoding="utf-8")
    before = path.read_bytes()
    monkeypatch.setattr("sys.argv", ["wavelab-inspect", str(path)])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result[0]["sampling"]["sample_count"] == 2
    assert result[0]["channel_statistics"][0]["max"] == 2
    assert path.read_bytes() == before
    monkeypatch.setattr("sys.argv", ["wavelab-inspect", str(tmp_path / "missing.csv")])
    assert main() == 1
    assert "error" in json.loads(capsys.readouterr().out)[0]

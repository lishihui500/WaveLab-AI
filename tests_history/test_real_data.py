"""Local private fixtures, independent CSV oracle, full-matrix equality."""
import csv
import hashlib
from pathlib import Path

import numpy as np
import pytest

from wavelab.domain import DatasetManifest
from wavelab.domain.mapping import map_group
from wavelab.ingest import parse_file, reopen_file

FIXTURES = Path(__file__).resolve().parents[1] / "test" / "fixtures"
CASES = [
    ("Y相上桥臂过流闭锁.txt", 4, 303, 1.49798, 1.50402, "bdd00813b3f61cffe6f2024c60e5f3df0e7d8aaf766dca1c14aa8c00924efdcf"),
    ("X相下桥臂故障电流.txt", 4, 63, 1.19966, 1.20090, "e01090d2c6e94a2512c84b4ec27db10c4a86cebf28a1e0c20e4082a8e064bbfe"),
    ("Full_Ucap.txt", 6, 17503, 1.88998, 2.24002, "c6cf9fc5a7b412e086145dd9dc935098c4885cce5195b9577b9a1978118ad89c"),
    ("A相上桥臂故障后三相线电压.txt", 3, 3503, 2.47098, 2.54102, "18caeea35f4c4eb8cb0dced7abf44511a5219dc2c009edae6a05ea1fd4624f32"),
    ("测试集1.txt", 6, 25003, 1.29998, 1.80002, "573e311de60ba4108df0d144dd67a69fab41f2c7aa8093974d95fc7b39edb2f7"),
    ("测试集2.txt", 5, 100002, 0.0, 2.00002, "e676f93685a62951bd52873f7e8ff8e017af02295f519fff91920d0e9544aa33"),
]


@pytest.mark.parametrize("name,channels,count,start,end,sha", CASES)
def test_real_full_matrix(name, channels, count, start, end, sha):
    path = FIXTURES / name
    assert path.is_file(), f"Required local acceptance fixture missing: {path}"
    before = path.read_bytes()
    assert hashlib.sha256(before).hexdigest() == sha
    # Independent reference: no production parser, grouping or row filters reused.
    records = list(csv.reader(before.decode("utf-8-sig").splitlines()))
    headers = tuple(records[0])
    reference = np.array([[float(cell) for cell in row] for row in records[1:]
                          if row and any(cell.strip() for cell in row)], dtype=np.float64)
    dataset = parse_file(path)
    meta = dataset.manifest
    assert meta.raw_headers == headers
    assert dataset.samples.shape == (count, channels + 1)
    np.testing.assert_array_equal(dataset.samples, reference)
    assert meta.sampling.start_s == start
    assert meta.sampling.end_s == end
    assert meta.sampling.uniform is True
    assert meta.sampling.dt_median_s == pytest.approx(20e-6, abs=1e-12)
    assert meta.sampling.sampling_rate_hz == pytest.approx(50000)
    assert len({c.channel_id for c in meta.channels}) == channels
    for index, channel in enumerate(meta.channels, 1):
        assert channel.source_column_index == index
        assert channel.raw_header == headers[index]
        np.testing.assert_array_equal(dataset.values(channel.channel_id), reference[:, index])
        assert channel.physical_role is None
        assert channel.unit is None
    if name == "测试集2.txt":
        assert [(g.group_name, len(g.channel_ids)) for g in meta.groups] == [("uG1YH", 3), ("uG2YH", 1), ("uG3YH", 1)]
        assert [w.code for w in meta.warnings] == ["empty_trailing_rows"]
        assert meta.warnings[0].line_numbers == (100004,)
    else:
        assert not meta.warnings
    assert path.read_bytes() == before


def test_confirmed_six_arm_mapping_and_json_reopen(tmp_path):
    path = FIXTURES / "测试集1.txt"
    original = parse_file(path)
    mapped = map_group(original.manifest, "Udc_cap_SC", "six_arms", unit="kV",
                       confirmation_source="WaveLab_AI_Handoff.md section 3.1: user-confirmed order for 测试集1.txt")
    saved = tmp_path / "manifest.json"
    saved.write_text(mapped.model_dump_json(indent=2), encoding="utf-8")
    restored = DatasetManifest.model_validate_json(saved.read_text(encoding="utf-8"))
    reopened = reopen_file(path, restored)
    assert reopened.manifest == mapped
    assert [c.physical_role for c in mapped.channels] == ["A相上桥臂", "A相下桥臂", "B相上桥臂", "B相下桥臂", "C相上桥臂", "C相下桥臂"]
    assert [c.channel_id for c in mapped.channels] == [c.channel_id for c in original.manifest.channels]
    np.testing.assert_array_equal(reopened.samples, original.samples)


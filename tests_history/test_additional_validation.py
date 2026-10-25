import numpy as np
import pytest
from pydantic import ValidationError

from wavelab.domain import DatasetManifest
from wavelab.ingest import ParseError, parse_text, reopen_file


def test_quoted_header_and_bom():
    data = parse_text('\ufeffDomain," i,a"," i,a"\n0,1,2\n1,3,4')
    assert data.manifest.raw_headers == ("Domain", " i,a", " i,a")
    assert len(data.manifest.groups) == 1


def test_time_interval_overflow_is_explicit():
    with pytest.raises(ParseError, match="time_interval_overflow"):
        parse_text("Domain,x\n-1e308,1\n1e308,2")


def test_manifest_sampling_mismatch(tmp_path):
    path = tmp_path / "synthetic.csv"
    path.write_text("Domain,x\n0,1\n1,2", encoding="utf-8")
    from wavelab.ingest import parse_file
    meta = parse_file(path).manifest
    payload = meta.model_dump()
    payload["sampling"]["end_s"] = 2.0
    modified = DatasetManifest.model_validate(payload)
    with pytest.raises(ParseError, match="manifest_mismatch"):
        reopen_file(path, modified)


@pytest.mark.parametrize("mutation", ["groups", "physical_role", "extra_field", "nonfinite_sampling"])
def test_corrupt_metadata_rejected(mutation):
    payload = parse_text("Domain,x\n0,1\n1,2").manifest.model_dump()
    if mutation == "groups":
        payload["groups"][0]["channel_ids"] = ("other:col_1",)
    elif mutation == "physical_role":
        payload["channels"][0]["physical_role"] = "A相"
    elif mutation == "extra_field":
        payload["execute_python"] = "anything"
    else:
        payload["sampling"]["dt_median_s"] = np.inf
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(payload)


def test_cli_pipe_is_utf8_under_legacy_environment(tmp_path):
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys
    path = tmp_path / "中文.csv"
    path.write_text("Domain,电流\n0,1\n1,2", encoding="utf-8")
    env = dict(os.environ, PYTHONIOENCODING="ascii",
               PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run([sys.executable, "-m", "wavelab.cli", str(path)],
                            capture_output=True, env=env, check=True)
    report = json.loads(result.stdout.decode("utf-8"))
    assert report[0]["raw_headers"] == ["Domain", "电流"]
    assert Path(report[0]["source_path"]).name == "中文.csv"

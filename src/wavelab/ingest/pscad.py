"""Read PSCAD comma-separated TXT/CSV without mangling or dropping columns."""
import csv
import hashlib
import io
from pathlib import Path
from uuid import uuid4

import numpy as np

from wavelab.domain import Channel, ChannelGroup, Dataset, DatasetManifest, ImportWarning, SamplingInfo


class ParseError(ValueError):
    def __init__(self, code: str, message: str, line_number: int | None = None,
                 source_column_index: int | None = None):
        self.code = code
        self.line_number = line_number
        self.source_column_index = source_column_index
        location = f" at line {line_number}" if line_number is not None else ""
        if source_column_index is not None:
            location += f", column {source_column_index} (0-based)"
        super().__init__(f"{code}{location}: {message}")


def parse_file(path: str | Path, *, dataset_id: str | None = None) -> Dataset:
    source = Path(path).resolve()
    raw = source.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
        encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
    except UnicodeDecodeError:
        try:
            content = raw.decode("gb18030")
            encoding = "gb18030"
        except UnicodeDecodeError as exc:
            raise ParseError("encoding", "Expected UTF-8/BOM or GB18030 text") from exc
    return _parse(content, dataset_id, str(source), hashlib.sha256(raw).hexdigest(), encoding)


def parse_text(content: str, *, dataset_id: str | None = None) -> Dataset:
    """Clipboard/text input; hash refers to the supplied UTF-8 text bytes."""
    return _parse(content.lstrip("\ufeff"), dataset_id, None,
                  hashlib.sha256(content.encode("utf-8")).hexdigest(), "utf-8")


def _parse(content, dataset_id, source_path, sha256, encoding):
    reader = csv.reader(io.StringIO(content, newline=""), strict=True)
    try:
        headers = tuple(next(reader))
    except StopIteration as exc:
        raise ParseError("empty_file", "No header or samples") from exc
    except csv.Error as exc:
        raise ParseError("csv_syntax", str(exc), reader.line_num) from exc
    if len(headers) < 2 or headers[0].strip() != "Domain":
        raise ParseError("header", "First column must be Domain (seconds), followed by signals", 1)
    if any(not field.strip() for field in headers):
        raise ParseError("header", "Empty channel header", 1)
    rows, blank_lines, warnings = [], [], []
    previous_time = None
    try:
        for fields in reader:
            line = reader.line_num
            if all(not field.strip() for field in fields):
                blank_lines.append(line)
                continue
            if blank_lines:
                raise ParseError("interior_empty_row", "Empty rows occur before valid samples", blank_lines[0])
            if len(fields) != len(headers):
                raise ParseError("row_width", f"Expected {len(headers)} fields, got {len(fields)}", line)
            values = []
            for column, field in enumerate(fields):
                if not field.strip():
                    raise ParseError("missing_value", "Partially missing row cannot be removed", line, column)
                try:
                    value = float(field)
                except ValueError as exc:
                    raise ParseError("not_numeric", "Expected a numeric value", line, column) from exc
                if not np.isfinite(value):
                    raise ParseError("nonfinite", "NaN/Inf/overflow is not allowed", line, column)
                values.append(value)
            if previous_time is not None and values[0] <= previous_time:
                code = "duplicate_time" if values[0] == previous_time else "reversed_time"
                raise ParseError(code, "Domain must be strictly increasing; samples were not removed", line, 0)
            previous_time = values[0]
            rows.append(values)
    except csv.Error as exc:
        raise ParseError("csv_syntax", str(exc), reader.line_num) from exc
    if not rows:
        raise ParseError("no_samples", "No valid numeric samples")
    if blank_lines:
        warnings.append(ImportWarning(code="empty_trailing_rows", line_numbers=tuple(blank_lines),
                                      message=f"Ignored {len(blank_lines)} entirely empty trailing row(s)"))
    if encoding == "gb18030":
        warnings.append(ImportWarning(code="encoding_fallback", message="Decoded using GB18030 after UTF-8 failed"))
    matrix = np.asarray(rows, dtype=np.float64)
    time = matrix[:, 0]
    sampling_fields = dict(sample_count=len(time), start_s=float(time[0]), end_s=float(time[-1]))
    if len(time) == 1:
        sampling = SamplingInfo(**sampling_fields, uniform=None)
        warnings.append(ImportWarning(code="single_sample", message="Sampling interval cannot be determined"))
    else:
        with np.errstate(over="ignore"):
            dt = np.diff(time)
        if not np.isfinite(dt).all():
            raise ParseError("time_interval_overflow", "Time differences cannot be represented as float64")
        median = float(np.median(dt))
        uniform = bool(np.allclose(dt, median, rtol=1e-6, atol=1e-12))
        sampling = SamplingInfo(**sampling_fields, uniform=uniform,
                                dt_min_s=float(dt.min()), dt_max_s=float(dt.max()), dt_median_s=median,
                                sampling_rate_hz=1.0 / median if uniform else None)
        if not uniform:
            warnings.append(ImportWarning(code="nonuniform_sampling",
                                          message="Sampling intervals vary; all source samples retained"))
    identity = dataset_id if dataset_id is not None else uuid4().hex
    channels, group_members = [], {}
    for index, raw_header in enumerate(headers[1:], 1):
        name = raw_header.strip()
        members = group_members.setdefault(name, [])
        channel_id = f"{identity}:col_{index}"
        channels.append(Channel(channel_id=channel_id, source_column_index=index, raw_header=raw_header,
                                group_name=name, group_index=len(members), display_name=f"{name}[{len(members)+1}]"))
        members.append(channel_id)
    groups = tuple(ChannelGroup(group_name=name, channel_ids=tuple(ids)) for name, ids in group_members.items())
    manifest = DatasetManifest(dataset_id=identity, source_path=source_path, source_sha256=sha256,
                               encoding=encoding, raw_headers=headers, channels=tuple(channels), groups=groups,
                               sampling=sampling, warnings=tuple(warnings))
    return Dataset(manifest, matrix)


def reopen_file(path: str | Path, manifest: DatasetManifest) -> Dataset:
    """Reimport with persisted identity/mapping; reject changed source bytes."""
    dataset = parse_file(path, dataset_id=manifest.dataset_id)
    if dataset.manifest.source_sha256 != manifest.source_sha256:
        raise ParseError("source_changed", "Source SHA-256 differs from persisted manifest")
    if (dataset.manifest.raw_headers != manifest.raw_headers
            or dataset.manifest.sampling != manifest.sampling):
        raise ParseError("manifest_mismatch", "Headers/sampling differ from persisted manifest")
    restored = manifest.model_copy(update={"source_path": dataset.manifest.source_path})
    return Dataset(restored, dataset.samples)


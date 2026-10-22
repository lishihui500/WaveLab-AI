"""Immutable metadata and original float64 samples; names are never keys."""
from dataclasses import dataclass
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Metadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ImportWarning(Metadata):
    code: str
    message: str
    line_numbers: tuple[int, ...] = ()


class SamplingInfo(Metadata):
    sample_count: int = Field(ge=1)
    start_s: float
    end_s: float
    uniform: bool | None
    dt_min_s: float | None = None
    dt_max_s: float | None = None
    dt_median_s: float | None = None
    sampling_rate_hz: float | None = None
    tolerance_rtol: float = 1e-6
    tolerance_atol_s: float = 1e-12


class ConfirmedQuantity(Metadata):
    preset_id: str | None = None
    zh: str = Field(min_length=1)
    en: str = Field(min_length=1)
    unit: str | None = Field(default=None, min_length=1, exclude=True)
    confirmation_source: str = Field(min_length=1)

    @model_validator(mode="after")
    def nonblank(self):
        if not all(value.strip() for value in (self.zh, self.en, self.confirmation_source)) or (self.unit is not None and not self.unit.strip()):
            raise ValueError("Confirmed quantity requires bilingual names, unit and confirmation source")
        return self


class Channel(Metadata):
    quantity: ConfirmedQuantity | None = None
    channel_id: str
    source_column_index: int = Field(ge=1)
    raw_header: str
    group_name: str
    group_index: int = Field(ge=0)
    display_name: str
    unit: str | None = None
    physical_role: str | None = None
    confirmation_source: str | None = None
    @model_validator(mode="after")
    def align_unit_alias(self):
        if self.quantity and self.quantity.unit != self.unit:
            object.__setattr__(self,"quantity",self.quantity.model_copy(update={"unit":self.unit}))
        return self



class ChannelGroup(Metadata):
    group_name: str
    channel_ids: tuple[str, ...]


class DatasetManifest(Metadata):
    schema_version: Literal["0.1"] = "0.1"
    dataset_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_-]+$")
    source_path: str | None
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    encoding: str
    raw_headers: tuple[str, ...]
    channels: tuple[Channel, ...]
    groups: tuple[ChannelGroup, ...]
    sampling: SamplingInfo
    warnings: tuple[ImportWarning, ...] = ()

    @model_validator(mode="after")
    def check_identity(self):
        if len(self.raw_headers) < 2 or self.raw_headers[0].strip() != "Domain":
            raise ValueError("First header must be Domain and at least one signal is required")
        if len(self.channels) != len(self.raw_headers) - 1:
            raise ValueError("Channel count does not match original headers")
        expected_groups: dict[str, list[str]] = {}
        for index, channel in enumerate(self.channels, 1):
            name = self.raw_headers[index].strip()
            members = expected_groups.setdefault(name, [])
            if (channel.source_column_index != index
                    or channel.channel_id != f"{self.dataset_id}:col_{index}"
                    or channel.raw_header != self.raw_headers[index]
                    or channel.group_name != name
                    or channel.group_index != len(members)):
                raise ValueError("Channel identity/order/group differs from source")
            if channel.physical_role is not None and not channel.confirmation_source:
                raise ValueError("Physical role requires a confirmation source")
            members.append(channel.channel_id)
        expected = [(name, tuple(ids)) for name, ids in expected_groups.items()]
        if [(g.group_name, g.channel_ids) for g in self.groups] != expected:
            raise ValueError("Group membership/order differs from source")
        return self


@dataclass(frozen=True)
class Dataset:
    manifest: DatasetManifest
    samples: np.ndarray

    def __post_init__(self):
        matrix = np.asarray(self.samples, dtype=np.float64)
        if matrix.shape != (self.manifest.sampling.sample_count, len(self.manifest.raw_headers)):
            raise ValueError("Sample matrix shape differs from manifest")
        # Bytes-backed ndarray cannot be made writable through setflags or a view.
        immutable = np.frombuffer(matrix.tobytes(), dtype=np.float64).reshape(matrix.shape)
        object.__setattr__(self, "samples", immutable)

    @property
    def time_s(self) -> np.ndarray:
        return self.samples[:, 0]

    def values(self, channel_id: str) -> np.ndarray:
        for channel in self.manifest.channels:
            if channel.channel_id == channel_id:
                return self.samples[:, channel.source_column_index]
        raise KeyError(channel_id)

    def with_manifest(self, manifest):
        """Metadata-only view of the same immutable bytes, without a matrix copy."""
        for name in ("dataset_id", "source_sha256", "raw_headers", "sampling"):
            if getattr(manifest,name) != getattr(self.manifest,name):
                raise ValueError("数据视图不得改变源身份或样本布局")
        view = object.__new__(Dataset)
        object.__setattr__(view,"manifest",manifest)
        object.__setattr__(view,"samples",self.samples)
        return view


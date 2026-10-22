"""Validated drawing intent. No generated code or waveform arrays in this schema."""
import math
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .models import DatasetManifest, Metadata


Limits = tuple[float, float]


def ordered_limits(value):
    if value is not None and (not all(math.isfinite(v) for v in value) or value[0] >= value[1]):
        raise ValueError("Axis limits must be finite and strictly increasing")
    return value


class BilingualText(Metadata):
    zh: str = ""
    en: str = ""

    def resolve(self, language: str, fallback: str) -> str:
        return getattr(self, language) or fallback


class LanguageSpec(Metadata):
    legend: Literal["zh", "en"] = "zh"
    axes: Literal["zh", "en"] = "zh"


class PageSpec(Metadata):
    preset: Literal["ieee_single_column", "ieee_double_column", "custom"] = "ieee_double_column"
    width_in: float | None = Field(default=None, ge=2, le=20)
    height_in: float | None = Field(default=None, ge=1.5, le=30)
    font_size_pt: float = Field(default=9, ge=6, le=24)
    axes_font_size_pt: float | None = Field(default=None, ge=6, le=32)
    title_font_size_pt: float | None = Field(default=None, ge=6, le=32)
    panel_spacing: float = Field(default=0.035, ge=0, le=1)
    legend_spacing: float = Field(default=0.16, ge=0.05, le=1)
    dpi: int = Field(default=300, ge=72, le=1200)
    font_family: str = Field(default="SimSun", min_length=1)

    @model_validator(mode="after")
    def custom_width(self):
        if self.preset == "custom" and self.width_in is None:
            raise ValueError("Custom page requires width_in")
        if self.preset != "custom" and self.width_in is not None:
            raise ValueError("IEEE preset fixes width; choose custom to override")
        return self

    @property
    def width(self):
        return self.width_in if self.preset == "custom" else (3.5 if self.preset == "ieee_single_column" else 7.16)


class TimeAxisSpec(Metadata):
    mode: Literal["absolute", "relative"] = "absolute"
    unit: Literal["s", "ms", "μs"] = "s"
    event_time_s: float | None = None
    xlim: Limits | None = None
    label: str | None = None
    label_i18n: BilingualText = Field(default_factory=BilingualText)

    _limits = field_validator("xlim")(ordered_limits)

    @model_validator(mode="after")
    def relative_origin(self):
        if self.mode == "relative" and self.event_time_s is None:
            raise ValueError("Relative time requires explicit event_time_s")
        if self.mode == "absolute" and self.event_time_s is not None:
            raise ValueError("event_time_s is only meaningful for relative time")
        return self


class SeriesSpec(Metadata):
    legend_source: Literal["custom", "channel"] = Field(default="channel", exclude=True)
    channel_id: str = Field(pattern=r"^[A-Za-z0-9_-]+:col_[1-9][0-9]*$")
    label: str | None = Field(default=None, exclude=True)
    label_i18n: BilingualText = Field(default_factory=BilingualText, exclude=True)
    unit: str | None = Field(default=None, exclude=True)
    physical_role: str | None = Field(default=None, exclude=True)
    confirmation_source: str | None = Field(default=None, exclude=True)
    color: str | None = None
    linestyle: Literal["-", "--", "-.", ":"] = "-"
    visible: bool = True
    linewidth_pt: float = Field(default=0.9, gt=0, le=5)

    @field_validator("color")
    @classmethod
    def valid_color(cls, value):
        if value is not None:
            from matplotlib.colors import is_color_like
            if not is_color_like(value):
                raise ValueError("Color must be a valid Matplotlib color")
        return value

    @model_validator(mode="after")
    def role_source(self):
        if self.physical_role is not None and not (self.confirmation_source or "").strip():
            raise ValueError("Explicit physical_role requires confirmation_source")
        return self


class InsetSpec(Metadata):
    """Physical seconds, with geometry relative to the owning panel axes."""
    id: str = Field(min_length=1)
    channel_ids: tuple[str, ...] = ()  # empty: inherit all currently visible series
    xlim_s: Limits
    ylim: Limits | None = None
    bounds: tuple[float, float, float, float] = (0.56, 0.52, 0.40, 0.40)
    show_region: bool = True
    show_connectors: bool = True

    _limits = field_validator("xlim_s", "ylim")(ordered_limits)

    @model_validator(mode="after")
    def geometry(self):
        x, y, width, height = self.bounds
        if (not all(math.isfinite(v) for v in self.bounds) or min(x, y) < 0
                or min(width, height) <= 0 or x + width > 1 or y + height > 1):
            raise ValueError("Inset bounds must fit inside the parent axes (x,y,width,height)")
        if len(set(self.channel_ids)) != len(self.channel_ids):
            raise ValueError("Duplicate inset channel id")
        return self


class PanelSpec(Metadata):
    plot_mode: Literal["analog", "digital_tracks"] = "analog"
    display_unit: str | None = Field(default=None, min_length=1, exclude=True)
    quantity_preset_id: str | None = Field(default=None, exclude=True)
    id: str = Field(min_length=1)
    title: str = ""
    title_i18n: BilingualText = Field(default_factory=BilingualText)
    ylabel_i18n: BilingualText = Field(default_factory=BilingualText, exclude=True)
    ylabel_mode: Literal["confirmed", "custom", "preset"] = Field(default="confirmed", exclude=True)
    ylabel: str = Field(default="幅值", exclude=True)
    ylim: Limits | None = None
    xlim: Limits | None = None
    series: tuple[SeriesSpec, ...] = ()
    insets: tuple[InsetSpec, ...] = ()
    scientific_y: Literal["auto", "always", "never"] = "auto"

    _limits = field_validator("ylim", "xlim")(ordered_limits)

    @model_validator(mode="after")
    def distinct_series(self):
        if len({s.channel_id for s in self.series}) != len(self.series):
            raise ValueError("A channel may appear only once per panel")
        return self


class LegendSpec(Metadata):
    show_units: bool = Field(default=False, exclude=True)
    axis_show_units: bool = Field(default=True, exclude=True)
    location: Literal["outside_top", "outside_right", "upper right", "upper left", "lower right", "lower left", "none"] = "outside_top"
    font_size_pt: float | None = Field(default=None, ge=6, le=32)
    font_family: str | None = None
    columns: int | None = Field(default=None, ge=1, le=12)


class EventSpec(Metadata):
    time_s: float
    label: str = Field(min_length=1)
    label_i18n: BilingualText = Field(default_factory=BilingualText)
    confirmation_source: str = Field(min_length=1)
    panel_ids: tuple[str, ...] = ()  # empty means every panel
    color: str = "#555555"
    linestyle: Literal["--", ":", "-.", "-"] = "--"

    _color = field_validator("color")(SeriesSpec.valid_color.__func__)

    @field_validator("confirmation_source")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Event meaning requires a nonblank confirmation source")
        return value


class FigureSpec(Metadata):
    schema_version: Literal["0.4"] = "0.4"
    migration_notes: tuple[str, ...] = Field(default=(), exclude=True)
    languages: LanguageSpec = Field(default_factory=LanguageSpec)

    @model_validator(mode="before")
    @classmethod
    def migrate_v02(cls, value):
        from wavelab.channel_migration import migrate_attributes
        return migrate_attributes(value)
    datasets: tuple[DatasetManifest, ...] = Field(min_length=1)
    page: PageSpec = Field(default_factory=PageSpec)
    time_axis: TimeAxisSpec = Field(default_factory=TimeAxisSpec)
    share_time_axis: bool = True
    panels: tuple[PanelSpec, ...] = Field(min_length=1, max_length=12)
    legend: LegendSpec = Field(default_factory=LegendSpec)
    events: tuple[EventSpec, ...] = ()

    @model_validator(mode="after")
    def references(self):
        if len({d.dataset_id for d in self.datasets}) != len(self.datasets):
            raise ValueError("Duplicate dataset_id in figure")
        panel_ids = {p.id for p in self.panels}
        if len(panel_ids) != len(self.panels):
            raise ValueError("Duplicate panel id")
        channels = {c.channel_id: c for d in self.datasets for c in d.channels}
        inset_ids = set()
        for panel in self.panels:
            for inset in panel.insets:
                if inset.id in inset_ids:
                    raise ValueError("Duplicate inset id")
                inset_ids.add(inset.id)
                if not set(inset.channel_ids) <= channels.keys():
                    raise ValueError("Inset references unknown channel ids")
            for series in panel.series:
                if series.channel_id not in channels:
                    raise ValueError(f"Panel {panel.id}: unknown channel_id {series.channel_id}")
        if self.share_time_axis:
            limits = {p.xlim for p in self.panels if p.xlim is not None}
            if self.time_axis.xlim is not None:
                limits.add(self.time_axis.xlim)
            if len(limits) > 1:
                raise ValueError("Shared time axes require identical xlim")
        for event in self.events:
            if not set(event.panel_ids) <= panel_ids:
                raise ValueError("Event references an unknown panel id")
        return self


def save_spec(spec: FigureSpec, path: str | Path):
    target = Path(path).resolve()
    if target.suffix.lower() != ".json":
        raise ValueError("FigureSpec destination must be .json")
    if any(d.source_path and Path(d.source_path).resolve() == target for d in spec.datasets):
        raise ValueError("Cannot overwrite a dataset source")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(spec.model_dump_json(indent=2), encoding="utf-8")


def load_spec(path: str | Path) -> FigureSpec:
    return FigureSpec.model_validate_json(Path(path).read_text(encoding="utf-8-sig"))

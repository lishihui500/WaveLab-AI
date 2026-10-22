"""Local workbench services. FigureSpec is the sole editable drawing state."""
from copy import deepcopy
import hashlib
import json
import os
import logging
from pathlib import Path
import re
from uuid import uuid4

from wavelab.domain import Dataset
from wavelab.domain.figure import FigureSpec, PanelSpec, SeriesSpec
from wavelab.domain.mapping import map_group
from wavelab.ingest import parse_file, reopen_file
from wavelab.render.engine import render_figure, export_figure, PALETTE


def safe_name(name):
    if not re.fullmatch(r"[\w\- .\u4e00-\u9fff]{1,80}", name) or name.strip(". ") != name:
        raise ValueError("名称仅可包含中英文、数字、空格、点、下划线、短横线，最多 80 字符")
    if name.split('.')[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raise ValueError("请避开 Windows 保留文件名")
    return name


def immutable_copy(raw: bytes, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (hashlib.sha256(raw).hexdigest() + ".txt")
    try:
        with path.open("xb") as stream:
            stream.write(raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError("本地数据副本损坏；未覆盖，请检查磁盘")
    return path


def validate_digital_panels(spec, datasets):
    from wavelab.render.digital import track_values
    for panel in spec.panels:
        if panel.plot_mode == "digital_tracks":
            for series in panel.series:
                if series.visible:
                    data = next(d for d in datasets.values()
                                if any(c.channel_id == series.channel_id for c in d.manifest.channels))
                    track_values(panel, series.channel_id, data.values(series.channel_id))


class Workbench:
    def __init__(self, root: str | Path):
        self._model_schema_type = FigureSpec
        self.root = Path(root).resolve()
        self.spec: FigureSpec | None = None
        self.data: dict[str, Dataset] = {}
        self._dataset_views = {}
        self.names: dict[str, str] = {}
        self.undo_stack: list[FigureSpec] = []
        self.redo_stack: list[FigureSpec] = []
        self.revision = 0
        self.project_epoch = uuid4().hex
        self.history_epoch = 0
        self.saved_spec = None
        self.project_path = None
        self.save_error = None
        self.migration_notes = []

    @property
    def save_status(self):
        if self.save_error:
            return "保存失败"
        return "已保存" if self.spec is not None and self.spec == self.saved_spec else "未保存修改"

    @property
    def datasets(self):
        # Metadata always comes from the current FigureSpec, including after undo.
        result = {}
        for manifest in self.spec.datasets if self.spec else ():
            source = self.data[manifest.dataset_id]
            cached = self._dataset_views.get(manifest.dataset_id)
            if cached is None or cached[0] is not source or cached[1].manifest != manifest:
                view = source if source.manifest == manifest else source.with_manifest(manifest)
                cached = (source, view)
                self._dataset_views[manifest.dataset_id] = cached
            result[manifest.dataset_id] = cached[1]
        return result

    def commit(self, payload):
        """Atomic validated replacement used by every manual/structured command."""
        candidate = FigureSpec.model_validate(payload)
        validate_digital_panels(candidate, self.data)
        for manifest in candidate.datasets:
            original = self.data.get(manifest.dataset_id)
            if original is None:
                raise ValueError("配置引用了尚未导入的数据集")
            # Display metadata can change; immutable source identity cannot.
            for field in ("source_path", "source_sha256", "raw_headers", "sampling", "groups", "encoding", "warnings"):
                if getattr(manifest, field) != getattr(original.manifest, field):
                    raise ValueError(f"不得修改数据身份字段: {field}")
        if candidate == self.spec:
            return
        if self.spec:
            self.undo_stack.append(self.spec)
            self.undo_stack = self.undo_stack[-50:]
        self.redo_stack.clear()
        self.spec = candidate
        self.revision += 1

    def reorder_panels(self, panel_ids):
        """Reorder whole immutable panels, reusing every series and loaded dataset."""
        panels = {p.id: p for p in self.spec.panels}
        ids = list(panel_ids)
        if len(ids) != len(panels) or len(set(ids)) != len(ids) or set(ids) != set(panels):
            raise ValueError("排序必须恰好包含全部现有 panel_id，且不得重复")
        payload = {name: getattr(self.spec, name) for name in type(self.spec).model_fields}
        payload["panels"] = tuple(panels[pid] for pid in ids)
        self.commit(payload)

    def move_panel(self, panel_id, target_index):
        ids = [p.id for p in self.spec.panels]
        if panel_id not in ids:
            raise ValueError(f"不存在的子图: {panel_id}")
        if type(target_index) is not int or not 0 <= target_index < len(ids):
            raise ValueError("目标位置必须是有效的从 0 开始的整数索引")
        ids.remove(panel_id)
        ids.insert(target_index, panel_id)
        self.reorder_panels(ids)

    def create_panel(self, panel_id, target_index=None):
        panels = list(self.spec.panels)
        if panel_id in {p.id for p in panels}:
            raise ValueError("新子图需要唯一 panel_id")
        if target_index is None:
            target_index = len(panels)
        if type(target_index) is not int or not 0 <= target_index <= len(panels):
            raise ValueError("插入位置越界")
        panels.insert(target_index, PanelSpec(id=panel_id))
        payload = {name: getattr(self.spec, name) for name in type(self.spec).model_fields}
        payload["panels"] = tuple(panels)
        self.commit(payload)

    def update(self, path: list[str | int], value):
        """Replace one validated field; unknown fields and references are rejected."""
        if not self.spec or not path or path[0] in {"datasets", "schema_version"}:
            raise ValueError("图形编辑需要有效路径；数据映射请使用专用接口")
        if (path[0]=='panels' and any(key in path for key in ('label','label_i18n','legend_source','unit','ylabel','ylabel_i18n','ylabel_mode','quantity_preset_id','display_unit'))) or (path[0]=='legend' and any(key in path for key in ('show_units','axis_show_units'))):
            raise ValueError("名称、物理量和单位只能通过通道属性表修改。")
        payload = self.spec.model_dump(mode="json")
        parent = payload
        for key in path[:-1]:
            parent = parent[key]
        if isinstance(parent, dict) and path[-1] not in parent:
            raise ValueError("未知图形属性")
        parent[path[-1]] = deepcopy(value)
        self.commit(payload)

    def undo(self):
        self.history_epoch += 1
        if self.undo_stack:
            self.redo_stack.append(self.spec)
            self.spec = self.undo_stack.pop()
            self.revision += 1

    def redo(self):
        self.history_epoch += 1
        if self.redo_stack:
            self.undo_stack.append(self.spec)
            self.spec = self.redo_stack.pop()
            self.revision += 1

    def import_bytes(self, raw: bytes, name: str):
        # Uploaded bytes and pasted UTF-8 content get a durable, exact copy now.
        path = immutable_copy(raw, self.root / "imports")
        data = parse_file(path)
        payload = data.manifest.model_dump()
        for channel in payload["channels"]:
            if len(next(g.channel_ids for g in data.manifest.groups if g.group_name == channel["group_name"])) == 1:
                channel["display_name"] = channel["group_name"]
        from wavelab.domain import DatasetManifest
        data = Dataset(DatasetManifest.model_validate(payload), data.samples)
        identity = data.manifest.dataset_id
        self.data[identity] = data
        self.names[identity] = Path(name).name
        if self.spec:
            payload = self.spec.model_dump(mode="json")
            payload["datasets"].append(data.manifest.model_dump(mode="json"))
        else:
            payload = FigureSpec(datasets=(data.manifest,), panels=(PanelSpec(id="panel_1"),)).model_dump()
        self.commit(payload)
        return identity

    def set_channel_properties(self, edits):
        """GUI uses the same validated atomic transaction as MCP."""
        from wavelab.commands.plot import Action, Plan, prepare, apply_proposal
        actions = [Action(action="set_channel_properties", channel_id=cid, changes=values,
                          evidence_quote=values.get("unit") or None) for cid, values in edits.items()]
        if not actions:
            return
        request = "用户在通道属性表明确确认源数据实际单位：" + "、".join(
            str(v.get("unit") or "未确认") for v in edits.values())
        apply_proposal(self, prepare(self, Plan(summary="保存通道属性", actions=actions), request))

    def edit_channels(self, dataset_id, edits):
        payload = self.spec.model_dump(mode="json")
        manifest = next(m for m in payload["datasets"] if m["dataset_id"] == dataset_id)
        allowed = {"display_name", "unit", "quantity"}
        channels = {c["channel_id"]: c for c in manifest["channels"]}
        for cid, values in edits.items():
            if not set(values) <= allowed:
                raise ValueError("仅允许编辑通道显示名称、单位与已确认物理量")
            if "unit" in values and values["unit"] != channels[cid]["unit"] and "quantity" not in values:
                channels[cid]["quantity"] = None
            channels[cid].update(values)
        self.commit(payload)

    def confirm_panel_quantity(self, panel_id, zh, en, unit):
        """One explicit local transaction; no import, AI, samples or style changes."""
        from wavelab.domain.models import ConfirmedQuantity
        quantity = ConfirmedQuantity(zh=zh.strip(), en=en.strip(), unit=unit.strip(),
                                     confirmation_source="用户在工作台确认子图全部曲线的物理量与单位")
        payload = self.spec.model_dump(mode="json")
        panel = next(p for p in self.spec.panels if p.id == panel_id)
        ids = {s.channel_id for s in panel.series if s.visible}
        if not ids:
            raise ValueError("请先为当前子图选择可见曲线")
        for manifest in payload["datasets"]:
            for channel in manifest["channels"]:
                if channel["channel_id"] in ids:
                    channel["quantity"] = quantity.model_dump(mode="json")
                    channel["unit"] = quantity.unit
        self.commit(payload)

    def set_channel_preset(self, channel_id, preset_id, unit):
        from wavelab.quantity_presets import QuantityLibrary, validate_quantity_unit
        from wavelab.domain.models import ConfirmedQuantity
        library = QuantityLibrary(self.root)
        preset = library.presets()[preset_id]
        validate_quantity_unit(preset, unit)
        manifest = next(m for m in self.spec.datasets if any(c.channel_id == channel_id for c in m.channels))
        quantity = ConfirmedQuantity(preset_id=preset.id, zh=preset.zh, en=preset.en, unit=unit,
                                     confirmation_source="用户明确选择物理量预设和源数据单位（不换算）")
        self.edit_channels(manifest.dataset_id, {channel_id: dict(unit=unit,quantity=quantity.model_dump(mode="json"))})
        try:
            library.remember(preset_id, unit)
        except (OSError, ValueError):
            logging.getLogger(__name__).warning("绘图已应用，最近物理量偏好未写入")

    def map_channels(self, dataset_id, group, template, confirmation, unit=None):
        payload = self.spec.model_dump(mode="json")
        original = next(m for m in self.spec.datasets if m.dataset_id == dataset_id)
        mapped = map_group(original, group, template, confirmation_source=confirmation, unit=unit)
        payload["datasets"] = [mapped.model_dump(mode="json") if m.dataset_id == dataset_id else m.model_dump(mode="json") for m in self.spec.datasets]
        self.commit(payload)

    def assign_channels(self, panel_id, channel_ids):
        payload = self.spec.model_dump(mode="json")
        target = next(p for p in payload["panels"] if p["id"] == panel_id)
        existing = {s["channel_id"]: s for s in target["series"]}
        target["series"] = [existing.get(cid, SeriesSpec(channel_id=cid, legend_source="channel").model_dump(mode="json")) for j, cid in enumerate(channel_ids)]
        self.commit(payload)

    def move_series(self, panel_id, channel_id, target_id):
        if panel_id == target_id:
            return
        payload = self.spec.model_dump(mode="json")
        source = next(p for p in payload["panels"] if p["id"] == panel_id)
        target = next(p for p in payload["panels"] if p["id"] == target_id)
        series = next(s for s in source["series"] if s["channel_id"] == channel_id)
        source["series"].remove(series)
        target["series"].append(series)
        self.commit(payload)

    def upsert_inset(self, panel_id, config):
        from wavelab.domain.figure import InsetSpec
        from wavelab.render.insets import validate_inset
        inset = InsetSpec.model_validate(config)
        panel = next(p for p in self.spec.panels if p.id == panel_id)
        validate_inset(inset, panel, self.datasets)
        payload = self.spec.model_dump(mode="json")
        target = next(p for p in payload["panels"] if p["id"] == panel_id)
        target["insets"] = [i for i in target["insets"] if i["id"] != inset.id]
        target["insets"].append(inset.model_dump(mode="json"))
        self.commit(payload)

    def remove_inset(self, panel_id, inset_id):
        payload = self.spec.model_dump(mode="json")
        target = next(p for p in payload["panels"] if p["id"] == panel_id)
        target["insets"] = [i for i in target["insets"] if i["id"] != inset_id]
        self.commit(payload)

    def set_time_unit(self, unit):
        from wavelab.quantity_presets import time_factor
        if unit not in {"s", "ms", "μs"}:
            raise ValueError("时间单位只支持 s / ms / μs")
        payload = self.spec.model_dump(mode="json")
        scale = time_factor(unit) / time_factor(self.spec.time_axis.unit)
        payload["time_axis"]["unit"] = unit
        for target in [payload["time_axis"], *payload["panels"]]:
            if target["xlim"] is not None:
                target["xlim"] = [v * scale for v in target["xlim"]]
        self.commit(payload)

    def set_display_unit(self, panel_id, unit):
        raise ValueError("独立显示单位已取消；由通道属性自动确定并检查数值换算。")

    def configure_panel_quantity(self, panel_id, source_unit, display_unit, *, preset_id=None, zh=None, en=None):
        if source_unit != display_unit:
            raise ValueError("旧的子图显示单位覆盖已取消，请使用 set_channel_properties。")
        panel = next(p for p in self.spec.panels if p.id == panel_id)
        self.set_channel_properties({s.channel_id:dict(quantity_name=preset_id or zh or en or '',unit=source_unit)
                                     for s in panel.series if s.visible})

    def set_axis_quantity(self, panel_id, preset_id, unit=None):
        raise ValueError("独立纵轴物理量已取消，请使用 set_channel_properties。")

    def sync_legends(self, targets, *, follow=False):
        raise ValueError("图例始终读取通道名称，无需单独同步或覆盖。")

    def preset(self, language, page_preset, preserve_languages=False):
        payload = self.spec.model_dump(mode="json")
        if not preserve_languages:
            payload["languages"] = dict(legend=language, axes=language)
        payload["page"].update(preset=page_preset, width_in=None, font_family="SimSun" if language == "zh" else "Times New Roman")
        if preserve_languages:
            payload["legend"]["font_family"] = "SimSun" if self.spec.languages.legend == "zh" else "Times New Roman"
        else:
            payload["legend"]["font_family"] = None
        self.commit(payload)

    def set_languages(self, legend, axes):
        payload = self.spec.model_dump(mode="json")
        payload["languages"] = dict(legend=legend, axes=axes)
        # Preserve custom fonts; adapt the two built-in academic defaults.
        if self.spec.page.font_family in {"SimSun", "Times New Roman"}:
            payload["page"]["font_family"] = "SimSun" if axes == "zh" else "Times New Roman"
        if self.spec.legend.font_family in {None, "SimSun", "Times New Roman"}:
            payload["legend"]["font_family"] = "SimSun" if legend == "zh" else "Times New Roman"
        self.commit(payload)

    def save_project(self, name):
        try:
            path = self._save_project(name)
        except (ValueError, OSError, TypeError) as exc:
            self.save_error = str(exc)
            logging.getLogger(__name__).exception("Project save failed: %s", name)
            try:
                self.root.mkdir(parents=True, exist_ok=True)
                with (self.root / "save_errors.log").open("a", encoding="utf-8") as log:
                    log.write(f"{name}: {type(exc).__name__}: {exc}\n")
            except OSError:
                pass
            raise
        self.saved_spec = self.spec
        self.project_path = path
        self.save_error = None
        return path

    def _save_project(self, name):
        if not self.spec:
            raise ValueError("请先导入数据")
        folder = self.root / "projects" / safe_name(name)
        payload = self.spec.model_dump(mode="json")
        for manifest in payload["datasets"]:
            raw = Path(manifest["source_path"]).read_bytes()
            if hashlib.sha256(raw).hexdigest() != manifest["source_sha256"]:
                raise ValueError("数据副本哈希不匹配；保存中止")
            path = immutable_copy(raw, folder / "data")
            manifest["source_path"] = path.relative_to(folder).as_posix()
        document = dict(project_version="1", figure=payload, dataset_names={m.dataset_id: self.names.get(m.dataset_id, m.dataset_id) for m in self.spec.datasets})
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / (uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(json.dumps(document, ensure_ascii=False, indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            check = json.loads(temporary.read_text(encoding="utf-8"))
            FigureSpec.model_validate(check["figure"])
            if check != document:
                raise ValueError("工程写入校验失败")
            os.replace(temporary, folder / "project.json")
        finally:
            temporary.unlink(missing_ok=True)
        return folder / "project.json"

    def open_project(self, path):
        path = Path(path).resolve()
        document = json.loads(path.read_text(encoding="utf-8-sig"))
        if document.get("project_version") != "1":
            raise ValueError("不支持的工程版本")
        spec = FigureSpec.model_validate(document["figure"])
        migration_notes = list(spec.migration_notes)
        restored = {}
        for manifest in spec.datasets:
            if not manifest.source_path:
                raise ValueError("工程缺少数据副本引用")
            source = (path.parent / manifest.source_path).resolve()
            if not source.is_relative_to(path.parent / "data"):
                raise ValueError("工程数据必须来自工程内部 data 目录")
            restored[manifest.dataset_id] = reopen_file(source, manifest)
        payload = spec.model_dump(mode="json")
        payload["datasets"] = [d.manifest.model_dump(mode="json") for d in restored.values()]
        candidate = FigureSpec.model_validate(payload)
        validate_digital_panels(candidate, restored)
        self.spec, self.data = candidate, restored
        self.migration_notes = migration_notes
        self.saved_spec = candidate
        self.project_path = path
        self.save_error = None
        self.names = document.get("dataset_names", {})
        self.project_epoch = uuid4().hex
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.revision += 1

    def open_spec(self, raw, base_dir="."):
        """Read a standalone spec and internalize its sources before editing."""
        spec = FigureSpec.model_validate_json(raw)
        migration_notes = list(spec.migration_notes)
        datasets = {}
        for manifest in spec.datasets:
            if not manifest.source_path:
                raise ValueError("该 JSON 没有持久化数据路径；请打开完整工程")
            source = Path(base_dir) / manifest.source_path
            data = reopen_file(source, manifest)
            copy_path = immutable_copy(source.read_bytes(), self.root / "imports")
            datasets[manifest.dataset_id] = Dataset(data.manifest.model_copy(update={"source_path": str(copy_path)}), data.samples)
        payload = spec.model_dump(mode="json")
        payload["datasets"] = [d.manifest.model_dump(mode="json") for d in datasets.values()]
        candidate = FigureSpec.model_validate(payload)
        self.data = datasets
        self.migration_notes = migration_notes
        self.spec = candidate
        self.saved_spec = None
        self.project_path = None
        self.save_error = None
        self.names = {m.dataset_id: Path(m.source_path).name for m in spec.datasets}
        self.project_epoch = uuid4().hex
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.revision += 1

    def export(self, name, formats=("pdf", "png", "svg"), bilingual=True):
        safe_name(name)
        folder = self.root / "exports" / uuid4().hex
        paths, notes = [], []
        datasets = self.datasets
        for language in (("zh", "en") if bilingual else (None,)):
            payload = self.spec.model_dump(mode="json")
            if language:
                payload["languages"] = dict(legend=language, axes=language)
                payload["page"]["font_family"] = "SimSun" if language == "zh" else "Times New Roman"
                payload["legend"]["font_family"] = None
            view = FigureSpec.model_validate(payload)
            result = render_figure(view, datasets)
            notes.extend(result.warnings)
            for fmt in formats:
                paths.append(export_figure(result, folder / f"{name}{'_' + language if language else ''}.{fmt}"))
            result.figure.clear()
        return paths, tuple(dict.fromkeys(notes))

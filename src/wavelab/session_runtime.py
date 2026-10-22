"""Upgrade live sessions, including nested models, without re-reading source data."""
import importlib
import sys
from threading import RLock

RUNTIME_SCHEMA_VERSION = 8
QUANTITY_PICKER_SYNC = True
if "_upgrade_lock" not in globals():
    _upgrade_lock = RLock()
_REQUIRED_API = ("create_panel", "move_panel", "reorder_panels", "set_channel_preset",
                 "set_axis_quantity", "set_display_unit", "configure_panel_quantity", "set_channel_properties")


def ensure_current_runtime():
    """Refresh only loaded dependencies of an actually obsolete unit schema."""
    with _upgrade_lock:
        models = importlib.import_module("wavelab.domain.models")
        figure = importlib.import_module("wavelab.domain.figure")
        obsolete = (figure.FigureSpec.model_fields["schema_version"].default != "0.4"
                    or "preset_id" not in models.ConfirmedQuantity.model_fields
                    or "plot_mode" not in figure.PanelSpec.model_fields
                    or "display_unit" not in figure.PanelSpec.model_fields
                    or "quantity_preset_id" not in figure.PanelSpec.model_fields
                    or figure.DatasetManifest is not models.DatasetManifest
                    or "μs" not in figure.TimeAxisSpec.model_fields["unit"].annotation.__args__
                    or models.ConfirmedQuantity.model_fields["unit"].is_required()
                    or not hasattr(models.Dataset, "with_manifest"))
        if obsolete:
            # These consumers bind classes at import time. Refreshing only the
            # models would split validators and services across class generations.
            names = ("domain.models", "domain", "domain.mapping", "domain.figure",
                     "ingest.pscad", "ingest", "units", "render.insets", "render.engine",
                     "app_preview", "channel_properties", "workbench", "commands.plot", "commands", "ai.provider",
                     "ai.assistant", "ai.manual", "ai.ui", "ai.manual_ui", "ai", "local_bridge")
            for name in names:
                module = sys.modules.get("wavelab." + name)
                if module is not None:
                    importlib.reload(module)
        commands = sys.modules.get("wavelab.commands.plot")
        if commands is not None and "set_channel_properties" not in commands.ALLOWED:
            for name in ("display_units", "workbench", "commands.plot", "commands", "ai.assistant", "ai.manual", "ai.ui", "ai.manual_ui", "ai", "local_bridge"):
                module = sys.modules.get("wavelab." + name)
                if module is not None:
                    importlib.reload(module)
        # The entrypoint may also be newer than the cached UI helper signature.
        # This helper is stateless; reloading it preserves all session data.
        ui = sys.modules.get("wavelab.quantity_ui")
        if ui is not None:
            from inspect import signature
            if "sync_scope" not in signature(ui.preset_picker).parameters:
                importlib.reload(ui)


def upgrade_workbench_models(work):
    """Apply defaults at a JSON boundary; prepare all state before installing it."""
    from wavelab.domain.figure import FigureSpec
    from wavelab.domain.models import Dataset, DatasetManifest
    if getattr(work, "_model_schema_type", None) is FigureSpec:
        return False

    def restore(spec):
        if spec is None:
            return None
        # model_validate(old_model) can reject an old class or skip missing defaults.
        return FigureSpec.model_validate_json(spec.model_dump_json(warnings=False))

    spec, saved = restore(work.spec), restore(work.saved_spec)
    undo = [restore(s) for s in work.undo_stack]
    redo = [restore(s) for s in work.redo_stack]
    data = {}
    for identity, source in work.data.items():
        manifest = DatasetManifest.model_validate_json(source.manifest.model_dump_json(warnings=False))
        if type(source) is Dataset and type(source.manifest) is DatasetManifest and source.manifest == manifest:
            data[identity] = source
        else:
            # Source arrays already have an immutable bytes backing. Do not copy
            # them through Dataset.__init__ while rebuilding metadata wrappers.
            view = object.__new__(Dataset)
            object.__setattr__(view, "manifest", manifest)
            object.__setattr__(view, "samples", source.samples)
            data[identity] = view

    changed = work.spec is not None and (type(work.spec) is not FigureSpec or work.spec != spec)
    work.spec, work.saved_spec = spec, saved
    work.migration_notes = list(spec.migration_notes) if spec else []
    work.undo_stack[:], work.redo_stack[:] = undo, redo
    work.data.clear()
    work.data.update(data)
    work._dataset_views.clear()
    work._model_schema_type = FigureSpec
    if changed:
        work.revision += 1  # Old proposals must not silently cross a schema upgrade.
    return True


def session_workbench(state, root):
    with _upgrade_lock:
        ensure_current_runtime()
        service = importlib.import_module("wavelab.workbench")
        figure = importlib.import_module("wavelab.domain.figure")
        if (not all(callable(getattr(service.Workbench, name, None)) for name in _REQUIRED_API)
                or service.FigureSpec is not figure.FigureSpec):
            service = importlib.reload(service)
        current = service.Workbench
        if "workbench" not in state:
            state["workbench"] = current(root)
        work = state["workbench"]
        if type(work) is not current:
            if type(work).__module__ != current.__module__ or type(work).__name__ != current.__name__:
                raise TypeError("工作台会话类型不兼容；当前数据仍保留")
            work.__class__ = current
        upgrade_workbench_models(work)
        return work

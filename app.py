"""Launch with: python -m streamlit run app.py"""
from pathlib import Path
from io import BytesIO
from time import perf_counter
import zipfile

import streamlit as st

# Check cached modules before binding aliases to model-dependent services.
import importlib
import wavelab.session_runtime as session_runtime
if (getattr(session_runtime, "RUNTIME_SCHEMA_VERSION", None) != 8
        or not getattr(session_runtime, "QUANTITY_PICKER_SYNC", False)
        or "set_channel_properties" not in getattr(session_runtime, "_REQUIRED_API", ())):
    session_runtime = importlib.reload(session_runtime)
session_runtime.ensure_current_runtime()

from wavelab.domain.figure import FigureSpec, PanelSpec, EventSpec, BilingualText
from wavelab.app_preview import preview_png
import wavelab.ai.ui as assistant_ui
if getattr(assistant_ui, "ASSISTANT_UI_VERSION", None) != 2:
    assistant_ui = importlib.reload(assistant_ui)
from wavelab.ai.ui import assistant_panel
from wavelab.units import confirmed_y_axis
from wavelab.quantity_presets import QuantityLibrary, time_factor


ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="WaveLab AI · 科研绘图工作台", layout="wide")
st.markdown("<style>.block-container{padding-left:1.25rem;padding-right:1.25rem;padding-top:2rem} h3{font-size:1.25rem!important}</style>", unsafe_allow_html=True)
w = session_runtime.session_workbench(st.session_state, ROOT / ".wavelab")
quantity_library = QuantityLibrary(w.root)
if getattr(w,"migration_notes",None):
    with st.expander("旧工程属性已统一，请检查通道表", expanded=True):
        for migration_note in w.migration_notes:
            st.info(migration_note)
        if st.button("已检查，关闭迁移提示"):
            w.migration_notes=[]
            st.rerun()


# Background HTTP threads only enqueue. This fragment executes on this session's
# Streamlit script thread, sharing all manual edits and undo history.
from uuid import uuid4
from wavelab.local_bridge import get_bridge

if "mcp_session_id" not in st.session_state:
    st.session_state.mcp_session_id = uuid4().hex
bridge = get_bridge(ROOT / ".wavelab" / "runtime")
bridge.attach(st.session_state.mcp_session_id)


@st.fragment(run_every=0.5)
def poll_local_tools():
    if bridge.drain(st.session_state.mcp_session_id, w):
        st.session_state.pop("exports", None)
        st.session_state.notice = "Codex 绘图修改已应用，可使用撤销恢复。"
        st.rerun()
    # Keep the upper connection status current without moving queue processing
    # ahead of the manual widgets or adding another periodic fragment.
    target = bridge.request("get_edit_target", {}).get("target", {})
    if target != st.session_state.get("codex_target_identity", {}):
        st.rerun()


def codex_connection():
    """Connection controls live with the assistant; queue draining stays last."""
    st.markdown("**Codex 对话绘图**")
    if not hasattr(bridge, "bind_target"):
        st.warning("请先保存工程，再重启 WaveLab 和 Codex MCP 连接。")
        return
    sid = st.session_state.mcp_session_id
    target = bridge.request("get_edit_target", {}).get("target", {})
    st.session_state.codex_target_identity = target
    bound = target.get("session_id") == sid and target.get("project_epoch") == w.project_epoch
    name = w.project_path.parent.name if w.project_path else "未保存工程"
    st.caption(name + (" · 已设为 Codex 编辑目标" if bound else " · 当前会话未绑定"))
    bind, unbind = st.columns([2, 1])
    if bind.button("设为 Codex 编辑目标", disabled=w.spec is None or bound):
        bridge.bind_target(sid, w)
        st.rerun()
    if bound and unbind.button("解除 Codex 编辑目标"):
        bridge.unbind_target(sid)
        st.rerun()
    st.caption("选定目标后，在 Codex 中直接描述绘图要求；需要保存时请明确提出。")
    with st.expander("连接详情"):
        st.caption("会话 " + sid)
def run(action, *args, **kwargs):
    try:
        result = action(*args, **kwargs)
    except (ValueError, OSError, KeyError, IndexError, TypeError) as exc:
        st.error(str(exc))
        return None
    st.session_state.notice = f"`{result}`" if isinstance(result, Path) else "已提交绘图修改；预览已更新。"
    if action in (w.open_project, w.open_spec):
        st.session_state.pending_project_name = w.project_path.parent.name if w.project_path else "我的科研图"
        st.session_state.pop("edit_error", None)
    st.session_state.pop("exports", None)
    st.rerun()


def limits(value):
    if not value.strip():
        return None
    parts = value.replace("，", ",").split(",")
    if len(parts) != 2:
        raise ValueError("范围格式：最小值, 最大值；留空表示自动")
    return [float(v.strip()) for v in parts]


def limits_text(value):
    return "" if value is None else f"{value[0]:g}, {value[1]:g}"


def auto(kind, title, *args, path, transform=lambda x: x, **kwargs):
    """One changed field, one validated commit, before the rerun renders."""
    key = "auto_" + repr(path) + "_" + str(w.revision)
    expected_state = (w.project_epoch, w.revision)
    def changed():
        if (w.project_epoch, w.revision) != expected_state:
            st.session_state.edit_error = "状态已变化，已忽略旧页面控件的输入；请按当前配置重新编辑。"
            return
        try:
            value = transform(st.session_state[key])
            if path[0] == "languages":
                languages = w.spec.languages.model_dump()
                languages[path[1]] = value
                w.set_languages(**languages)
            elif path == ["time_axis", "unit"]:
                w.set_time_unit(value)
            elif path == ["share_time_axis"]:
                payload = w.spec.model_dump(mode="json")
                payload["share_time_axis"] = value
                if value:
                    for panel in payload["panels"]:
                        panel["xlim"] = None
                w.commit(payload)
            else:
                w.update(path, value)
            st.session_state.pop("edit_error", None)
            st.session_state.pop("exports", None)
        except (ValueError, OSError, KeyError, TypeError) as exc:
            st.session_state.edit_error = f"修改未提交，保留上一份有效配置：{exc}"
    return getattr(st, kind)(title, *args, key=key, on_change=changed, **kwargs)


def bi_inputs(prefix, value, path=None):
    a, b = st.container(), st.container()
    if path is not None:
        with a:
            zh = auto("text_input", prefix + " · 中文", value.zh, path=path + ["zh"])
        with b:
            en = auto("text_input", prefix + " · English", value.en, path=path + ["en"])
        return dict(zh=zh, en=en)
    return {"zh": a.text_input(prefix + " · 中文", value.zh), "en": b.text_input(prefix + " · English", value.en)}


@st.cache_data(max_entries=8, show_spinner=False)
def preview(spec_json, _datasets, data_token):
    start = perf_counter()
    output, notes, geometry = preview_png(FigureSpec.model_validate_json(spec_json), _datasets, geometry=True)
    return output, notes, perf_counter() - start, geometry


st.title("WaveLab AI")
st.caption("科研波形绘图工作台")
error_message = st.empty()
if error := st.session_state.get("edit_error"):
    error_message.error(error)
notice_message = st.empty()
if notice := st.session_state.pop("notice", None):
    notice_message.success(notice)

with st.sidebar:
    st.header("工程操作")
    if "pending_project_name" in st.session_state:
        st.session_state.project_name = st.session_state.pop("pending_project_name")
    if "project_name" not in st.session_state:
        st.session_state.project_name = w.project_path.parent.name if w.project_path else "我的科研图"
    project_name = st.text_input("工程名称", key="project_name")
    status = st.empty()
    status.info(w.save_status)
    if st.button("保存工程", disabled=w.spec is None, type="primary"):
        status.info("保存中")
        try:
            path = w.save_project(project_name)
            st.session_state.notice = f"工程已保存：`{path}`"
            st.rerun()
        except (ValueError, OSError, TypeError) as exc:
            status.error("保存失败")
            st.error(f"保存失败，当前图形已保留：{exc}；日志：{w.root / 'save_errors.log'}")
    if w.save_error:
        st.error(w.save_error)
    st.header("数据与工程")
    with st.expander("导入 TXT / CSV", expanded=w.spec is None):
        uploads = st.file_uploader("选择数据文件", type=["txt", "csv"], accept_multiple_files=True)
        if st.button("导入上传文件", disabled=not uploads):
            def import_all():
                for upload in uploads:
                    w.import_bytes(upload.getvalue(), upload.name)
            run(import_all)
        local = st.text_input("本地数据文件路径", placeholder=r"C:\…\测试集1.txt")
        if st.button("导入本地文件", disabled=not local):
            def import_local():
                path = Path(local.strip().strip('"'))
                if path.suffix.lower() not in {".txt", ".csv"}:
                    raise ValueError("请选择 TXT 或 CSV")
                w.import_bytes(path.read_bytes(), path.name)
            run(import_local)
    with st.expander("粘贴 PSCAD 数据"):
        paste_name = st.text_input("粘贴数据名称", "粘贴数据")
        pasted = st.text_area("含 Domain 表头的数据", height=130)
        if st.button("导入粘贴文本", disabled=not pasted):
            run(w.import_bytes, pasted.encode("utf-8"), paste_name)
    with st.expander("保存 / 打开工程", expanded=w.spec is None):
        projects = sorted((w.root / "projects").glob("*/project.json"))
        chosen_project = st.selectbox("已保存工程", projects, format_func=lambda p: p.parent.name, index=0 if projects else None)
        if st.button("打开所选工程", disabled=chosen_project is None):
            run(w.open_project, chosen_project)
        project_path = st.text_input("或输入 project.json 路径")
        if st.button("从路径打开工程", disabled=not project_path):
            run(w.open_project, project_path.strip().strip('"'))
        st.caption("迁移时请复制整个工程目录。")
    with st.expander("读取 FigureSpec JSON"):
        config = st.file_uploader("上传旧版或新版绘图配置", type=["json"])
        base = st.text_input("相对数据路径基目录", str(ROOT))
        if st.button("载入配置", disabled=config is None):
            run(w.open_spec, config.getvalue(), base)

assistant_panel(w, codex_connection=codex_connection)

if w.spec is None:
    poll_local_tools()
    st.info("从左侧导入数据或打开工程。")
    st.stop()

spec = w.spec
rev = str(w.revision)
ds_id = st.selectbox("数据集", [m.dataset_id for m in spec.datasets], format_func=lambda i: w.names.get(i, i), key="dataset")
manifest = next(m for m in spec.datasets if m.dataset_id == ds_id)
from wavelab import channel_properties_ui
if getattr(channel_properties_ui, "UI_VERSION", None) != 3:
    importlib.reload(channel_properties_ui)
from wavelab.channel_properties_ui import channel_properties_editor
channel_properties_editor(w, manifest, quantity_library, run)
left, center, right = st.columns([1.15, 2.4, 1.85], gap="medium")
def select_panel(source, destination):
    st.session_state[destination] = st.session_state[source]

with left:
    st.subheader("① 通道")
    sample = manifest.sampling
    dt_text = f"{sample.dt_median_s:.6g}" if sample.dt_median_s is not None else "未知"
    st.caption(f"{sample.sample_count:,} 点 · {len(manifest.channels)} 通道\n\n{sample.start_s:g}–{sample.end_s:g} s · Δt 中位数 {dt_text} s")
    for warning in manifest.warnings:
        st.warning(f"{warning.code}: {warning.message}")
    with st.expander("原始列及采样信息"):
        st.dataframe([{"源列": c.source_column_index, "原始名称": c.raw_header, "显示名称": c.display_name, "单位": c.unit or "未确认", "ID": c.channel_id} for c in manifest.channels], hide_index=True)
        st.caption(f"均匀采样：{sample.uniform}；Δt 范围：{sample.dt_min_s}–{sample.dt_max_s} s")
    panel_ids = [p.id for p in spec.panels]
    target_id = st.selectbox("目标子图", panel_ids, key="target_panel", on_change=select_panel, args=("target_panel", "edit_panel"))
    target = next(p for p in spec.panels if p.id == target_id)
    selected = []
    with st.form("channels_" + ds_id + "_" + target_id + "_" + rev):
        for group in manifest.groups:
            with st.expander(group.group_name, expanded=True):
                selected += st.multiselect("选择子通道 · " + group.group_name, list(group.channel_ids), default=[s.channel_id for s in target.series if s.channel_id in group.channel_ids], format_func=lambda cid: next(f"{c.display_name} · 列{c.source_column_index}" for c in manifest.channels if c.channel_id == cid))
        all_channels = st.checkbox("本数据集全部通道加入目标子图")
        if st.form_submit_button("应用通道选择"):
            selected = [c.channel_id for c in manifest.channels] if all_channels else selected
            keep = [s.channel_id for s in target.series if not s.channel_id.startswith(ds_id + ":")]
            run(w.assign_channels, target_id, keep + selected)

with center:
    st.subheader("② 画布与导出")
    undo, redo = st.columns(2)
    if undo.button("撤销", disabled=not w.undo_stack):
        run(w.undo)
    if redo.button("恢复", disabled=not w.redo_stack):
        run(w.redo)
    try:
        img, notes, elapsed, geometry = preview(spec.model_dump_json(), w.datasets, tuple((key, id(data.samples)) for key, data in w.data.items()))
        if st.checkbox("启用鼠标框选与局部图拖动", value=False):
            from wavelab.inset_interaction import inset_canvas, apply_gesture
            gesture = inset_canvas(img, geometry, w.revision)
            if gesture and gesture.get("nonce") != st.session_state.get("last_inset_gesture"):
                st.session_state.last_inset_gesture = gesture.get("nonce")
                try:
                    pending = apply_gesture(w, gesture)
                    if pending:
                        st.session_state.pending_inset = (w.revision, pending)
                    else:
                        st.rerun()
                except (ValueError, KeyError, TypeError) as exc:
                    st.error(str(exc))
            if pending_state := st.session_state.get("pending_inset"):
                pending_revision, pending = pending_state
                st.caption(f"待确认框选：{pending}")
                confirm_selection, cancel_selection = st.columns(2)
                if confirm_selection.button("确认框选并创建局部图"):
                    from uuid import uuid4
                    if pending_revision != w.revision:
                        st.error("配置已改变，请重新框选")
                    else:
                        st.session_state.pop("pending_inset", None)
                        run(w.upsert_inset, pending["panel_id"], dict(id="inset_" + uuid4().hex[:12], xlim_s=pending["xlim_s"], ylim=pending["ylim"]))
                if cancel_selection.button("取消框选"):
                    st.session_state.pop("pending_inset", None)
                    st.rerun()
        else:
            st.image(img, width="stretch")
        st.caption(f"图宽 {spec.page.width:g} in · 预览 {elapsed:.3f} s")
        if notes:
            with st.expander(f"标签回退 / 字体 / 排版提示（{len(notes)}）", expanded=True):
                for note in notes:
                    st.warning(note)
    except (ValueError, OSError) as exc:
        st.error(f"预览失败：{exc}")
    with st.expander("导出论文图", expanded=True):
        export_name = st.text_input("输出名称", "MMC_Fault")
        formats = st.multiselect("输出格式", ["pdf", "png", "svg"], default=["pdf", "png", "svg"])
        a, b = st.columns(2)
        dual = a.button("一键导出中英文", disabled=not formats)
        current = b.button("导出当前视图", disabled=not formats)
        if dual or current:
            try:
                paths, warnings = w.export(export_name, formats, bilingual=dual)
                st.session_state.exports = (paths, warnings)
            except (ValueError, OSError) as exc:
                st.error(str(exc))
        if "exports" in st.session_state:
            paths, warnings = st.session_state.exports
            st.success(f"已生成 {len(paths)} 个文件：{paths[0].parent}")
            for path in paths:
                st.download_button(path.name, path.read_bytes(), file_name=path.name, key=str(path))
            buf = BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in paths:
                    archive.writestr(path.name, path.read_bytes())
            st.download_button("下载全部图形 ZIP", buf.getvalue(), file_name=export_name + "_figures.zip")
            if warnings:
                with st.expander("导出提示"):
                    st.write(list(warnings))
        st.download_button("导出 FigureSpec JSON", spec.model_dump_json(indent=2), file_name=export_name + ".json")

with right:
    st.subheader("③ 绘图设置")
    st.caption("设置自动应用，可撤销；通道属性与事件需点击保存。")
    with st.expander("子图", expanded=True):
        panel_id = st.selectbox("编辑子图", panel_ids, key="edit_panel", on_change=select_panel, args=("edit_panel", "target_panel"))
        index = panel_ids.index(panel_id)
        panel = spec.panels[index]
        auto("selectbox", "信号显示方式", ["analog", "digital_tracks"],
             index=["analog", "digital_tracks"].index(panel.plot_mode),
             format_func=lambda value: {"analog": "连续量曲线", "digital_tracks": "数字量分层轨道（0/1 阶梯）"}[value],
             path=["panels", index, "plot_mode"])
        from wavelab.panel_order import panel_order, apply_order_gesture
        gesture = panel_order(spec.panels, w.revision, w.project_epoch)
        if gesture and gesture != st.session_state.get("last_panel_order_gesture"):
            st.session_state.last_panel_order_gesture = gesture
            run(apply_order_gesture, w, gesture)
        insertion = st.selectbox("新子图插入位置", ["添加到末尾", "在当前子图上方插入", "在当前子图下方插入"])
        if st.button("添加子图", disabled=len(panel_ids) >= 12):
            new_id = next(f"panel_{n}" for n in range(1, 100) if f"panel_{n}" not in panel_ids)
            run(w.create_panel, new_id, None if insertion == "添加到末尾" else index + (insertion == "在当前子图下方插入"))
        if st.button("删除所选子图", disabled=len(panel_ids) == 1):
            def delete_panel():
                payload = spec.model_dump(mode="json")
                payload["panels"].pop(index)
                events = []
                for event in payload["events"]:
                    if event["panel_ids"]:
                        event["panel_ids"] = [i for i in event["panel_ids"] if i != panel_id]
                        if not event["panel_ids"]:
                            continue
                    events.append(event)
                payload["events"] = events
                w.commit(payload)
            run(delete_panel)
        with st.container():
            title = bi_inputs("子图标题", panel.title_i18n, ["panels", index, "title_i18n"])
    with st.expander("X 轴：时间、单位与范围", expanded=True):
        with st.container():
            t = spec.time_axis
            mode = auto("selectbox", "时间模式", ["absolute", "relative"], index=["absolute", "relative"].index(t.mode), path=["time_axis"], transform=lambda v: dict(t.model_dump(mode="json"), mode=v, event_time_s=(t.event_time_s or 0) if v == "relative" else None))
            unit = auto("selectbox", "显示单位", ["s", "ms", "μs"], index=["s", "ms", "μs"].index(t.unit), path=["time_axis", "unit"])
            origin = auto("number_input", "相对时间零点 / s", value=float(t.event_time_s or 0), format="%.6f", disabled=t.mode != "relative", path=["time_axis", "event_time_s"])
            xl = auto("text_input", "X 范围（显示单位，逗号分隔）", limits_text(t.xlim), path=["time_axis", "xlim"], transform=limits)
            st.caption("时间单位仅影响显示；局部图使用绝对秒值。")
            if st.button("X 轴标题跟随时间单位"):
                run(w.update, ["time_axis"], dict(t.model_dump(mode="json"), label=None, label_i18n=dict(zh="", en="")))
            with st.expander("保留的 X 轴双语字段（不参与自动命名）"):
                xlabel = bi_inputs("X 轴标题", t.label_i18n, ["time_axis", "label_i18n"])
            shared = auto("checkbox", "多子图共享时间轴", spec.share_time_axis, path=["share_time_axis"])
            pxl = auto("text_input", "独立 X 范围（关闭共享后使用）", limits_text(panel.xlim), disabled=spec.share_time_axis, path=["panels", index, "xlim"], transform=limits)
    with st.expander("Y 轴范围与刻度", expanded=True):
        actual_zh, axis_warning = confirmed_y_axis(spec, panel, "zh")
        actual_en, _ = confirmed_y_axis(spec, panel, "en")
        st.caption(f"纵轴：{actual_zh} / {actual_en}")
        if axis_warning:
            st.warning(axis_warning)
        yl = auto("text_input", "Y 范围（逗号分隔）", limits_text(panel.ylim), path=["panels", index, "ylim"], transform=limits)
        if st.button("将当前 Y 范围应用到全部子图", disabled=panel.ylim is None):
            payload = spec.model_dump(mode="json")
            for target_panel in payload["panels"]:
                target_panel["ylim"] = list(panel.ylim)
            run(w.commit, payload)
    with st.expander("曲线与图例样式", expanded=True):
        with st.expander("图例位置、字体与排版"):
            lgap = auto("number_input", "顶部图例行间距", 0.05, 1., float(spec.page.legend_spacing), step=0.01, path=["page", "legend_spacing"])
            locs = ["outside_top", "outside_right", "upper right", "upper left", "lower right", "lower left", "none"]
            loc = auto("selectbox", "图例位置", locs, index=locs.index(spec.legend.location), path=["legend", "location"])
            cols = auto("number_input", "图例列数（0 自动）", 0, 12, spec.legend.columns or 0, path=["legend", "columns"], transform=lambda v: v or None)
            lfs = auto("number_input", "图例字号 / pt", 6., 32., float(spec.legend.font_size_pt or max(6, spec.page.font_size_pt - 1)), path=["legend", "font_size_pt"])
            lfont = auto("text_input", "图例字体（留空跟随主字体）", spec.legend.font_family or "", path=["legend", "font_family"], transform=lambda v: v or None)
        choices = [s.channel_id for s in panel.series]
        if choices:
            by_id = {c.channel_id: c for m in spec.datasets for c in m.channels}
            selected_channel = st.selectbox("编辑曲线", choices, format_func=lambda cid: panel_id + " · " + by_id[cid].display_name, key="curve_selector_" + panel_id)
            i = index
            j = next(n for n, series in enumerate(panel.series) if series.channel_id == selected_channel)
            curve = spec.panels[i].series[j]
            with st.container():
                color = auto("text_input", "颜色（留空使用科研配色）", curve.color or "", path=["panels", i, "series", j, "color"], transform=lambda v: v or None)
                style = auto("selectbox", "线型", ["-", "--", "-.", ":"], index=["-", "--", "-.", ":"].index(curve.linestyle), path=["panels", i, "series", j, "linestyle"])
                lw = auto("number_input", "线宽 / pt", 0.1, 5., float(curve.linewidth_pt), step=0.1, path=["panels", i, "series", j, "linewidth_pt"])
                visible = auto("checkbox", "显示曲线", curve.visible, path=["panels", i, "series", j, "visible"])
                destination = st.selectbox("曲线所属子图", panel_ids, index=i)
                if st.button("移动曲线", disabled=destination == spec.panels[i].id):
                    run(w.move_series, spec.panels[i].id, curve.channel_id, destination)
            if st.button("删除所选曲线"):
                run(w.update, ["panels", i, "series"], [s.model_dump(mode="json") for n, s in enumerate(spec.panels[i].series) if n != j])
        else:
            st.caption("请在左侧选择通道并应用。")
    with st.expander("局部放大图", expanded=False):
        from uuid import uuid4
        st.caption("时间按当前刻度输入；位置和尺寸相对于主图。")
        choices_inset = ["新增"] + [i.id for i in panel.insets]
        selected_inset = st.selectbox("编辑局部图", choices_inset, key="inset_selector_" + panel.id)
        current_inset = next((i for i in panel.insets if i.id == selected_inset), None)
        factor = time_factor(spec.time_axis.unit)
        origin_s = spec.time_axis.event_time_s or 0
        visible_series = [s.channel_id for s in panel.series if s.visible]
        if visible_series:
            dataset_for_window = next(d for d in w.datasets.values() if visible_series[0] in {c.channel_id for c in d.manifest.channels})
            physical_window = current_inset.xlim_s if current_inset else (float(dataset_for_window.time_s[0]), float(dataset_for_window.time_s[-1]))
            shown_window = [(v - origin_s) * factor for v in physical_window]
            with st.form("inset_form_" + panel.id + "_" + selected_inset + "_" + rev):
                all_visible = st.checkbox("继承主图全部可见曲线", not current_inset or not current_inset.channel_ids)
                available_ids = [s.channel_id for s in panel.series]
                names_inset = {c.channel_id: c.display_name for m in spec.datasets for c in m.channels}
                inset_channels = st.multiselect("局部图曲线", available_ids, default=[cid for cid in (current_inset.channel_ids if current_inset else visible_series) if cid in available_ids], format_func=lambda cid: names_inset[cid] + " · " + cid)
                start = st.number_input("局部开始时间（当前显示单位）", value=shown_window[0], format="%.9f")
                end = st.number_input("局部结束时间（当前显示单位）", value=shown_window[1], format="%.9f")
                inset_y = st.text_input("局部 Y 范围（留空自动）", limits_text(current_inset.ylim if current_inset else None))
                b = current_inset.bounds if current_inset else (0.56, 0.52, 0.4, 0.4)
                bx = st.number_input("局部图左侧位置", 0., 1., b[0], step=0.01)
                by = st.number_input("局部图底部位置", 0., 1., b[1], step=0.01)
                bw = st.number_input("局部图宽度", 0.01, 1., b[2], step=0.01)
                bh = st.number_input("局部图高度", 0.01, 1., b[3], step=0.01)
                region = st.checkbox("显示放大区域框", current_inset.show_region if current_inset else True)
                connectors = st.checkbox("显示连接线", current_inset.show_connectors if current_inset else True)
                if st.form_submit_button("添加局部放大图" if current_inset is None else "保存局部放大图"):
                    try:
                        config = dict(id=current_inset.id if current_inset else "inset_" + uuid4().hex[:12],
                                      channel_ids=[] if all_visible else inset_channels,
                                      xlim_s=[start / factor + origin_s, end / factor + origin_s],
                                      ylim=limits(inset_y), bounds=[bx, by, bw, bh],
                                      show_region=region, show_connectors=connectors)
                        if not all_visible and not inset_channels:
                            raise ValueError("请选择至少一条局部图曲线，或启用继承")
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        run(w.upsert_inset, panel.id, config)
        else:
            st.info("请先为主图添加可见曲线；已有局部图暂停绘制，配置保留。")
        if current_inset and st.button("删除局部放大图"):
            run(w.remove_inset, panel.id, current_inset.id)
    with st.expander("论文预设与语言", expanded=True):
        preset_key = "paper_preset_" + rev
        def change_preset(expected_state=(w.project_epoch, w.revision)):
            if (w.project_epoch, w.revision) != expected_state:
                st.session_state.edit_error = "状态已变化，已忽略旧页面论文预设的输入；请按当前配置重新编辑。"
                return
            value = st.session_state[preset_key]
            w.preset("zh" if value.startswith("中文") else "en", "ieee_single_column" if "单栏" in value else "ieee_double_column", preserve_languages=True)
            st.session_state.pop("exports", None)
        preset_index = 0 if spec.page.font_family == "SimSun" else (1 if spec.page.preset == "ieee_single_column" else 2)
        preset = st.selectbox("整体预设", ["中文科研绘图", "IEEE 英文单栏", "IEEE 英文双栏"], index=preset_index, key=preset_key, on_change=change_preset)
        with st.container():
            languages = {kind: auto("selectbox", title, ["zh", "en"], index=["zh", "en"].index(getattr(spec.languages, kind)), format_func=lambda x: "中文" if x == "zh" else "English", path=["languages", kind]) for kind, title in (("legend", "图例语言"), ("axes", "坐标轴与标题语言"))}
    with st.expander("图纸与字体"):
        with st.container():
            p = spec.page
            size = auto("selectbox", "尺寸预设", ["ieee_single_column", "ieee_double_column", "custom"], index=["ieee_single_column", "ieee_double_column", "custom"].index(p.preset), path=["page"], transform=lambda v: dict(p.model_dump(mode="json"), preset=v, width_in=p.width if v == "custom" else None))
            width = auto("number_input", "自定义宽度 / in", 2., 20., float(p.width), disabled=p.preset != "custom", path=["page", "width_in"])
            height = auto("number_input", "高度 / in（0 自动）", 0., 30., float(p.height_in or 0), path=["page", "height_in"], transform=lambda v: v or None)
            font = auto("text_input", "坐标与标题字体", p.font_family, path=["page", "font_family"])
            fs = auto("number_input", "基础字号 / pt", 6., 24., float(p.font_size_pt), path=["page", "font_size_pt"])
            afs = auto("number_input", "坐标标题字号 / pt", 6., 32., float(p.axes_font_size_pt or p.font_size_pt), path=["page", "axes_font_size_pt"])
            tfs = auto("number_input", "子图标题字号 / pt", 6., 32., float(p.title_font_size_pt or p.font_size_pt), path=["page", "title_font_size_pt"])
            dpi = auto("number_input", "导出 DPI", 72, 1200, p.dpi, path=["page", "dpi"])
            gap = auto("number_input", "子图间距", 0., 1., float(p.panel_spacing), step=0.01, path=["page", "panel_spacing"])
    with st.expander("事件标记"):
        event_index = st.selectbox("编辑事件", [-1] + list(range(len(spec.events))), format_func=lambda i: "新增事件" if i == -1 else f"{i + 1}. {spec.events[i].label}", key="event_" + rev)
        event = spec.events[event_index] if event_index >= 0 else EventSpec(time_s=0, label="事件", confirmation_source="用户手动指定")
        with st.form("event_form_" + str(event_index) + rev):
            et = st.number_input("事件绝对时刻 / s", value=float(event.time_s), format="%.6f")
            fallback = st.text_input("事件名称（回退）", event.label)
            labels = bi_inputs("事件名称", event.label_i18n)
            ec = st.text_input("事件颜色", event.color)
            es = st.selectbox("事件线型", ["--", ":", "-.", "-"], index=["--", ":", "-.", "-"].index(event.linestyle))
            ep = st.multiselect("显示于子图（留空全部）", panel_ids, default=list(event.panel_ids))
            if st.form_submit_button("保存事件"):
                events = [e.model_dump(mode="json") for e in spec.events]
                item = dict(time_s=et, label=fallback, label_i18n=labels, color=ec, linestyle=es, panel_ids=ep, confirmation_source="用户在工作台手动指定事件与时刻")
                if event_index < 0:
                    events.append(item)
                else:
                    events[event_index] = item
                run(w.update, ["events"], events)
        if st.button("删除事件", disabled=event_index < 0):
            run(w.update, ["events"], [e.model_dump(mode="json") for i, e in enumerate(spec.events) if i != event_index])

# Register polling after widgets so a remote rerun never interrupts their first
# registration or carries an earlier button trigger past unvisited controls.
poll_local_tools()

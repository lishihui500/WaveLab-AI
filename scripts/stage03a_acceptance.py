"""Local acceptance through Streamlit AppTest; private outputs stay in reports/."""
from pathlib import Path
import csv
import hashlib
import io
import json
import platform
import shutil
import sys
from time import perf_counter

import numpy as np
import streamlit
from streamlit.testing.v1 import AppTest

from wavelab.workbench import Workbench
from wavelab.render.engine import render_figure
from wavelab.domain.figure import FigureSpec


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "stage_03A"


def field(at, kind, label):
    return next(e for e in getattr(at, kind) if e.label == label)


def click(at, label):
    field(at, "button", label).click().run(timeout=60)
    if at.exception or at.error:
        raise AssertionError(str(at.exception) + str(at.error))


def start(filename):
    at = AppTest.from_file(ROOT / "app.py", default_timeout=60)
    at.session_state["workbench"] = Workbench(OUT / "workspace")
    at.run()
    field(at, "text_input", "本地数据文件路径").input(str(ROOT / "test" / "fixtures" / filename)).run()
    then = perf_counter()
    click(at, "导入本地文件")
    imported = perf_counter() - then
    field(at, "checkbox", "本数据集全部通道加入目标子图").check()
    then = perf_counter()
    click(at, "应用通道选择")
    return at, imported, perf_counter() - then


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    originals = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / "test" / "fixtures").glob("*.txt")}
    metrics = []
    scenarios = [("S1_six_arms", "测试集1.txt"), ("S2_long_waveform", "测试集2.txt"), ("S3_fault", "X相下桥臂故障电流.txt"), ("S4_capacitors", "Full_Ucap.txt")]
    for scene, filename in scenarios:
        at, imported, initial = start(filename)
        w = at.session_state["workbench"]
        if scene.startswith("S1"):
            field(at, "text_input", "映射单位（可留空）").input("kV")
            field(at, "checkbox", "我确认该变量组的通道顺序与所选模板一致").check()
            click(at, "保存确认映射")
            click(at, "添加子图")
            click(at, "添加子图")
            for source_column, destination in ((3, "panel_2"), (4, "panel_2"), (5, "panel_3"), (6, "panel_3")):
                # Select a currently present curve by stable source column ID.
                pair = next((i, j) for i, p in enumerate(w.spec.panels) for j, s in enumerate(p.series) if s.channel_id.endswith(f":col_{source_column}"))
                field(at, "selectbox", "编辑曲线").select(pair).run()
                field(at, "selectbox", "曲线所属子图").select(destination)
                click(at, "应用曲线属性")
        if scene.startswith("S2"):
            field(at, "text_input", "X 范围（显示单位，逗号分隔）").input("1, 1.04")
            click(at, "应用时间轴")
            field(at, "text_input", "Y 范围（逗号分隔）").input("-100, 100")
            click(at, "应用子图属性")
        if scene.startswith("S3"):
            field(at, "selectbox", "时间模式").select("relative")
            field(at, "selectbox", "显示单位").select("ms")
            field(at, "number_input", "相对时间零点 / s").set_value(1.2)
            click(at, "应用时间轴")
            field(at, "number_input", "事件绝对时刻 / s").set_value(1.2)
            field(at, "text_input", "事件名称（回退）").input("故障时刻")
            field(at, "text_input", "事件名称 · 中文").input("故障时刻")
            field(at, "text_input", "事件名称 · English").input("Fault inception")
            click(at, "保存事件")
        for pi, panel in enumerate(w.spec.panels):
            field(at, "selectbox", "编辑子图").select(panel.id).run()
            zh = f"{chr(65 + pi)}相" if scene.startswith("S1") else ""
            en = f"Phase {chr(65 + pi)}" if scene.startswith("S1") else ""
            yz, ye = ("电容电压和 (kV)", "Capacitor voltage sum (kV)") if scene.startswith("S1") else (("电流 (kA)", "Current (kA)") if scene.startswith("S3") else (("电压 (kV)", "Voltage (kV)") if scene.startswith("S4") else ("信号值（原始单位）", "Signal (original unit)")))
            field(at, "text_input", "子图标题 · 中文").input(zh)
            field(at, "text_input", "子图标题 · English").input(en)
            field(at, "text_input", "Y 轴标题 · 中文").input(yz)
            field(at, "text_input", "Y 轴标题 · English").input(ye)
            click(at, "应用子图属性")
        for i, panel in enumerate(w.spec.panels):
            for j, curve in enumerate(panel.series):
                field(at, "selectbox", "编辑曲线").select((i, j)).run()
                c = next(c for m in w.spec.datasets for c in m.channels if c.channel_id == curve.channel_id)
                en = f"Phase-{chr(65+i)} {'upper' if j == 0 else 'lower'} arm" if scene.startswith("S1") else c.display_name
                field(at, "text_input", "图例 · 中文").input(c.display_name)
                field(at, "text_input", "图例 · English").input(en)
                field(at, "selectbox", "线型").select("-" if j % 2 == 0 else "--")
                click(at, "应用曲线属性")
        field(at, "number_input", "图例列数（0 自动）").set_value(2 if scene.startswith("S1") else 3)
        field(at, "number_input", "高度 / in（0 自动）").set_value(6.6 if scene.startswith("S1") else 3.5)
        click(at, "应用图纸与图例")
        field(at, "text_input", "工程名称").input(scene).run()
        click(at, "保存工程")
        spec_before = w.spec
        field(at, "text_input", "输出名称").input(scene).run()
        t = perf_counter()
        click(at, "一键导出中英文")
        export_time = perf_counter() - t
        paths, warnings = at.session_state.exports
        assert w.spec == spec_before
        scene_folder = OUT / scene
        scene_folder.mkdir(exist_ok=True)
        for path in paths:
            shutil.copy2(path, scene_folder / path.name)
        (scene_folder / "figure.json").write_text(w.spec.model_dump_json(indent=2), encoding="utf-8")
        project = OUT / "workspace" / "projects" / scene / "project.json"
        new = Workbench(OUT / "reopened")
        new.open_project(project)
        assert new.spec.panels == w.spec.panels
        new.update(["page", "font_size_pt"], 10)
        new.undo()
        assert new.spec.panels == w.spec.panels
        sample = next(iter(new.datasets.values()))
        rows = list(csv.reader(io.StringIO((ROOT / "test" / "fixtures" / filename).read_text(encoding="utf-8-sig"))))
        expected = np.array([[float(v) for v in r] for r in rows[1:] if any(v.strip() for v in r)])
        np.testing.assert_array_equal(sample.samples, expected)
        layout = {}
        for language in ("zh", "en"):
            payload = w.spec.model_dump(mode="json")
            payload["languages"] = dict(legend=language, axes=language)
            payload["page"]["font_family"] = "SimSun" if language == "zh" else "Times New Roman"
            t = perf_counter()
            result = render_figure(FigureSpec.model_validate(payload), w.datasets)
            render_seconds = perf_counter() - t
            assert all(len(line.get_ydata()) == len(expected) for line in result.lines.values())
            renderer = result.figure.canvas.get_renderer()
            legends = [ax.get_legend() for ax in result.figure.axes if ax.get_legend()]
            outside = all(not legend.get_window_extent(renderer).overlaps(ax.bbox) for legend in legends for ax in result.axes.values())
            assert outside
            assert not any("Layout:" in note or "Glyph" in note for note in result.warnings)
            layout[language] = dict(font=result.font_family, render_seconds=render_seconds, warnings=result.warnings, legends_outside_data=outside)
            result.figure.clear()
        metrics.append(dict(scene=scene, source=filename, samples=len(expected), gui_import_seconds=imported, gui_first_plot_seconds=initial, gui_dual_export_seconds=export_time, layout=layout, export_warnings=warnings, project=str(project), source_matrix_exact=True, reopened_editable=True))
        print(scene, "OK", flush=True)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT / "test" / "fixtures").glob("*.txt")}
    assert after == originals
    report = dict(environment=dict(python=platform.python_version(), streamlit=streamlit.__version__, platform=platform.platform()), source_sha256=after, source_files_unchanged=True, scenarios=metrics)
    (OUT / "performance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    run()

"""Local-only reproducible acceptance scenarios. No uploads, no phase inference."""
import hashlib
import json
from pathlib import Path
import platform
from time import perf_counter

import matplotlib
import numpy as np
import pydantic

from wavelab.domain import Dataset
from wavelab.domain.figure import EventSpec, FigureSpec, PageSpec, PanelSpec, SeriesSpec, TimeAxisSpec, load_spec, save_spec
from wavelab.domain.mapping import map_group
from wavelab.ingest import parse_file
from .engine import export_figure, render_figure, reopen_datasets


def acceptance_cases(root: Path):
    fixtures = root / "test" / "fixtures"
    filenames = ["X相下桥臂故障电流.txt", "Y相上桥臂过流闭锁.txt", "测试集1.txt", "测试集2.txt", "Full_Ucap.txt", "A相上桥臂故障后三相线电压.txt"]
    ids = ("case_a", "case_b", "case_c", "case_d", "case_e", "case_f")
    loaded = [parse_file(fixtures / name, dataset_id=identity) for name, identity in zip(filenames, ids)]
    c = loaded[2]
    mapped = map_group(c.manifest, "Udc_cap_SC", "six_arms", unit="kV",
                       confirmation_source="WaveLab_AI_Handoff.md 3.1: user-confirmed six-arm order for 测试集1.txt")
    loaded[2] = Dataset(mapped, c.samples)

    def series(data, indexes, *, unit=None):
        return tuple(SeriesSpec(channel_id=data.manifest.channels[i-1].channel_id, unit=unit,
                                linestyle=("-", "--", "-.", ":", "-", "--")[j % 6])
                     for j, i in enumerate(indexes))

    a, b, c, d, e, f = loaded
    specs = [
        FigureSpec(datasets=(a.manifest,), page=PageSpec(height_in=2.6),
                   time_axis=TimeAxisSpec(mode="relative", unit="ms", event_time_s=1.2),
                   panels=(PanelSpec(id="currents", ylabel="电流 (kA)", series=series(a, [1, 2, 3, 4], unit="kA")),),
                   events=(EventSpec(time_s=1.2, label="故障时刻", confirmation_source="User stage-2 acceptance A: fault at 1.2 s"),)),
        FigureSpec(datasets=(b.manifest,), page=PageSpec(height_in=6.2),
                   panels=(PanelSpec(id="arms", title="(a) IarmT2 / IarmB2", ylabel="电流 (kA)", series=series(b, [1, 2], unit="kA")),
                           PanelSpec(id="dc", title="(b) IdP_SC", ylabel="电流 (kA)", series=series(b, [3], unit="kA")),
                           PanelSpec(id="difference", title="(c) IdiffP1", ylabel="电流 (kA)", series=series(b, [4], unit="kA"), scientific_y="always"))),
        FigureSpec(datasets=(c.manifest,), page=PageSpec(height_in=6.2),
                   panels=tuple(PanelSpec(id=f"phase_{phase}", title=f"({letter}) {phase}相", ylabel="电容电压和 (kV)",
                                          series=series(c, [2*i+1, 2*i+2]))
                                for i, (phase, letter) in enumerate(zip("ABC", "abc")))),
        FigureSpec(datasets=(d.manifest,), page=PageSpec(height_in=6.2),
                   panels=(PanelSpec(id="group1", title="(a) uG1YH：原序三个子通道", ylabel="信号值（原始单位）", series=series(d, [1, 2, 3])),
                           PanelSpec(id="group2", title="(b) uG2YH", ylabel="信号值（原始单位）", series=series(d, [4])),
                           PanelSpec(id="group3", title="(c) uG3YH", ylabel="信号值（原始单位）", series=series(d, [5])))),
        FigureSpec(datasets=(e.manifest,), page=PageSpec(preset="ieee_single_column", height_in=3.3),
                   panels=(PanelSpec(id="capacitors", ylabel="电压 (kV)", series=series(e, [1, 2, 3, 4, 5, 6], unit="kV")),)),
        FigureSpec(datasets=(f.manifest,), page=PageSpec(preset="ieee_single_column", height_in=2.7),
                   panels=(PanelSpec(id="line_voltages", ylabel="线电压 (kV)", series=series(f, [1, 2, 3], unit="kV")),)),
    ]
    names = ("A_fault_currents", "B_current_transients", "C_six_arms", "D_large_groups", "E_capacitors", "F_line_voltages")
    cases = list(zip(names, specs, loaded))
    detail = specs[3].model_dump()
    detail["time_axis"]["xlim"] = (1.0, 1.04)
    # Local zoom uses explicit y limits derived from existing samples in the
    # requested window. The entire unchanged series is still passed to Matplotlib.
    mask = (d.time_s >= 1.0) & (d.time_s <= 1.04)
    for panel_index, source_column in ((1, 4), (2, 5)):
        values = d.samples[mask, source_column]
        low, high = float(values.min()), float(values.max())
        margin = max((high - low) * 0.08, 1e-12)
        detail["panels"][panel_index]["ylim"] = (low - margin, high + margin)
    cases.append(("D_detail_40ms", FigureSpec.model_validate(detail), d))
    return cases


def generate(root: str | Path = "."):
    root = Path(root).resolve()
    out = root / "reports" / "stage_02"
    out.mkdir(parents=True, exist_ok=True)
    metrics = []
    for name, spec, dataset in acceptance_cases(root):
        source = Path(dataset.manifest.source_path)
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        original = dataset.samples.tobytes()
        save_spec(spec, out / f"{name}.json")
        loaded = load_spec(out / f"{name}.json")
        assert loaded == spec
        start = perf_counter()
        result = render_figure(loaded, {dataset.manifest.dataset_id: dataset})
        render_seconds = perf_counter() - start
        outputs = {}
        for fmt in ("pdf", "png", "svg"):
            start = perf_counter()
            path = export_figure(result, out / f"{name}.{fmt}")
            outputs[fmt] = {"seconds": perf_counter()-start, "bytes": path.stat().st_size}
        # Reopen the actual persisted FigureSpec/source and compare every series.
        start = perf_counter()
        replay = render_figure(loaded, reopen_datasets(loaded, base_dir=out))
        for key, line in result.lines.items():
            np.testing.assert_array_equal(line.get_xdata(), replay.lines[key].get_xdata())
            np.testing.assert_array_equal(line.get_ydata(), replay.lines[key].get_ydata())
        replay_seconds = perf_counter() - start
        assert original == dataset.samples.tobytes()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == before
        metrics.append({"case": name, "source": source.name, "samples": len(dataset.samples),
                        "curve_count": len(result.lines), "render_seconds": render_seconds,
                        "reopen_render_seconds": replay_seconds, "outputs": outputs,
                        "font": result.font_family, "warnings": result.warnings,
                        "source_unchanged": True, "dataset_unchanged": True,
                        "size_inches": result.figure.get_size_inches().tolist()})
        result.figure.clear()
        replay.figure.clear()
    report = {"environment": {"python": platform.python_version(), "platform": platform.platform(),
                               "matplotlib": matplotlib.__version__, "numpy": np.__version__,
                               "pydantic": pydantic.__version__, "style": "local IEEE equivalent; usetex=False"},
              "cases": metrics}
    (out / "performance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return report


if __name__ == "__main__":
    generate()

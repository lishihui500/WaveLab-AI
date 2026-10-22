"""Controlled cold-discovery vs warm-route comparison, isolated real-data copy.

This is not a live Streamlit latency benchmark. The owner thread pumps at 2ms.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from statistics import median
from time import sleep

from wavelab.local_bridge import Bridge, status
from wavelab.mcp_server import rpc, _routes
from wavelab.commands.plot import sample_hashes
from wavelab.workbench import Workbench


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / "reports" / "mcp_workflow_20261022"
    output.mkdir(parents=True, exist_ok=True)
    records = []
    with TemporaryDirectory(prefix="wavelab-route-benchmark-") as temporary:
        directory = Path(temporary) / "runtime"
        w = Workbench(Path(temporary) / "work")
        source = root / "test" / "fixtures" / "测试集1.txt"
        w.import_bytes(source.read_bytes(), source.name)
        w.assign_channels("panel_1", [c.channel_id for c in w.spec.datasets[0].channels])
        before = sample_hashes(w)
        bridge = Bridge(directory)
        try:
            for sid in ["gui", "other1", "other2", "other3", "other4"]:
                bridge.attach(sid)
            bridge.bind_target("gui", w)
            with ThreadPoolExecutor(1) as pool:
                def run(method, params=None):
                    pending = pool.submit(rpc, method, params, "gui", directory)
                    while not pending.done():
                        bridge.drain("gui", w)
                        sleep(.002)
                    result = pending.result()
                    assert "error" not in result, result
                    return result
                run("get_figure_context")  # warm schema/imports
                for strategy in ["rediscover_each_rpc", "cached_route"]:
                    for _ in range(10):
                        if strategy == "rediscover_each_rpc":
                            _routes.clear()
                        result = run("get_figure_context")
                        records.append(dict(strategy=strategy, **result["diagnostics"]))
                s = status(w, "gui")
                request = dict(expected_project_epoch=s["project_epoch"], expected_revision=s["revision"],
                               expected_fingerprint=s["fingerprint"], user_request="调整图例列数为2", actions=[dict(action="set_legend", changes=dict(columns=2))])
                result = run("apply_plot_actions", request)
                records.append(dict(strategy="atomic_action", **result["diagnostics"]))
                assert sample_hashes(w) == before
        finally:
            bridge.close()
    summary = {}
    for strategy in {r["strategy"] for r in records}:
        selected = [r for r in records if r["strategy"] == strategy]
        keys = {k for r in selected for k in r["stages_ms"]}
        summary[strategy] = dict(n=len(selected), median_ms={k: median(r["stages_ms"][k] for r in selected if k in r["stages_ms"]) for k in sorted(keys)})
    document = dict(scope="isolated HTTP bridge, real fixture copy, 5 sessions, one endpoint, 2ms test pump; not live GUI or historical full baseline",
                    samples_unchanged=True, summary=summary, records=records)
    (output / "benchmark.json").write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

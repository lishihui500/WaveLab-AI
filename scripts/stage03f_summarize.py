"""Summarize recorded evidence only; never plans or executes drawing tasks."""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

TIMINGS = ("task_s", "end_to_end_s", "mcp_total_s", "apply_roundtrip_s", "save_export_s", "visual_check_s", "page_load_s", "render_s")
METHODS = ("codex_mcp", "gui_automation", "manual_gui", "chatgpt_json")


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def describe(values):
    return {"n": len(values), "mean": statistics.mean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "min": min(values) if values else None, "max": max(values) if values else None,
            "sample_std": statistics.stdev(values) if len(values) > 1 else None}


def summarize(root):
    records = []
    ids = set()
    for path in sorted((root / "trials").glob("*/record.json")):
        record = json.loads(path.read_text(encoding="utf-8-sig"))
        if record.get("trial_id") in ids:
            raise ValueError(f"Duplicate trial_id: {record.get('trial_id')}")
        if not record.get("trial_id") or record.get("task_id") not in ("F01", "F02", "F03") or record.get("method") not in METHODS:
            raise ValueError(f"Invalid identity: {path}")
        ids.add(record["trial_id"])
        for name, value in record.get("timing", {}).items():
            if name in TIMINGS and value is not None and not numeric(value):
                raise ValueError(f"Invalid duration {name}: {path}")
        record["record_path"] = str(path.relative_to(root))
        records.append(record)
    for method in ("manual_gui", "chatgpt_json"):
        for task in ("F01", "F02", "F03"):
            if not any(r["method"] == method and r["task_id"] == task for r in records):
                records.append({"trial_id": f"{method}_{task}_not_measured", "task_id": task,
                                "method": method, "status": "NOT_MEASURED", "timing": {},
                                "first_attempt_success": None, "final_success": None})
    groups = defaultdict(list)
    for row in records:
        groups[(row["task_id"], row["method"])].append(row)
    summary = []
    for (task, method), rows in sorted(groups.items()):
        executed = [r for r in rows if r.get("status") not in ("BLOCKED", "NOT_MEASURED")]
        summary.append({"task_id": task, "method": method, "records": len(rows), "executed_n": len(executed),
                        "statuses": {s: sum(r.get("status") == s for r in rows) for s in sorted({r.get("status", "UNKNOWN") for r in rows})},
                        "first_attempt_success_count": sum(r.get("first_attempt_success") is True for r in executed),
                        "first_attempt_observed_n": sum(isinstance(r.get("first_attempt_success"), bool) for r in executed),
                        "final_success_count": sum(r.get("final_success") is True for r in executed),
                        "final_observed_n": sum(isinstance(r.get("final_success"), bool) for r in executed),
                        "timing": {key: describe([r.get("timing", {}).get(key) for r in executed if numeric(r.get("timing", {}).get(key))]) for key in TIMINGS},
                        "mcp_calls": describe([r["mcp_calls"] for r in executed if numeric(r.get("mcp_calls"))]),
                        "interaction_count": describe([r["interaction_count"] for r in executed if numeric(r.get("interaction_count"))])})
    comparable = defaultdict(lambda: defaultdict(list))
    for r in records:
        if r.get("final_success") is True and r.get("baseline_semantic_hash") and r.get("timing_boundary_id") and numeric(r.get("timing", {}).get("task_s")):
            comparable[(r["task_id"], r["baseline_semantic_hash"], r["timing_boundary_id"])][r["method"]].append(r["timing"]["task_s"])
    ratios = []
    for (task, base, boundary), methods in comparable.items():
        if methods.get("codex_mcp") and methods.get("gui_automation"):
            denominator = statistics.mean(methods["codex_mcp"])
            if denominator:
                ratios.append({"task_id": task, "baseline_semantic_hash": base, "timing_boundary_id": boundary,
                               "gui_mean_divided_by_mcp_mean": statistics.mean(methods["gui_automation"]) / denominator,
                               "gui_n": len(methods["gui_automation"]), "mcp_n": len(methods["codex_mcp"])})
    return records, summary, ratios


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1] / "reports/stage_03F")
    args = parser.parse_args()
    root = args.root
    records, summaries, ratios = summarize(root)
    root.mkdir(parents=True, exist_ok=True)
    def write(name, value):
        (root / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    write("benchmark_results.json", {"schema_version": 1, "records": records})
    write("statistics.json", {"groups": summaries, "same_boundary_ratios": ratios,
                              "notes": ["Missing observations remain null, never zero.", "Failures retained; durations include recorded failed trials.", "GUI automation is not human GUI.", "No ratio across unequal timing boundaries.", "No inferred pure reasoning time or token count."]})
    fields = ["trial_id", "task_id", "method", "status", "first_attempt_success", "final_success", "timing_boundary_id", "baseline_semantic_hash", "mcp_calls", "interaction_count", "recorded_successful_interaction_count", "retry_count", "parameter_errors", "revision_conflict", "human_intervention", "rerun_count", "timing_eligible", "raw_wall_task_s", "editing_interval_s", "drawing_save_export_wall_s", "transaction_success", "failed_checks", "screenshot_size_px", "started_at", "ended_at", *TIMINGS, "checks", "notes", "record_path"]
    with (root / "benchmark_results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in records:
            flat = {key: row.get(key) for key in fields}
            flat.update({key: row.get("timing", {}).get(key) for key in TIMINGS})
            for key in ("checks", "notes", "failed_checks", "screenshot_size_px"):
                if isinstance(flat[key], (dict, list)):
                    flat[key] = json.dumps(flat[key], ensure_ascii=False)
            writer.writerow(flat)
    print(json.dumps({"record_count": len(records), "groups": len(summaries), "same_boundary_ratios": len(ratios)}))


if __name__ == "__main__":
    main()

"""Static presentation charts and exact configuration differences from saved evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import statistics
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def diff(before, after, path=""):
    if type(before) is not type(after):
        return [{"path": path, "before": before, "after": after}]
    if isinstance(before, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            child = f"{path}/{key}"
            if key not in before:
                result.append({"path": child, "change": "added", "after": after[key]})
            elif key not in after:
                result.append({"path": child, "change": "removed", "before": before[key]})
            else:
                result.extend(diff(before[key], after[key], child))
        return result
    if isinstance(before, list):
        result = []
        for index in range(max(len(before), len(after))):
            child = f"{path}/{index}"
            if index >= len(before):
                result.append({"path": child, "change": "added", "after": after[index]})
            elif index >= len(after):
                result.append({"path": child, "change": "removed", "before": before[index]})
            else:
                result.extend(diff(before[index], after[index], child))
        return result
    return [] if before == after else [{"path": path, "before": before, "after": after}]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1]/"reports/stage_03F")
    args = parser.parse_args()
    root = args.root
    output = root/"figures"
    output.mkdir(parents=True, exist_ok=True)
    records = json.loads((root/"benchmark_results.json").read_text(encoding="utf-8"))["records"]
    records = [r for r in records if r.get("status") not in ("NOT_MEASURED", "BLOCKED")]
    methods = [("codex_mcp", "Codex + MCP", "#0072B2"), ("gui_automation", "GUI automation", "#D55E00")]
    tasks = ("F01", "F02", "F03")
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 10, "axes.grid": False,
                         "pdf.fonttype": 42, "svg.fonttype": "path"})
    def save(fig, stem):
        fig.text(.5, .015, "GUI automation ≠ human GUI. Human GUI / ChatGPT JSON: NOT_MEASURED.", ha="center", fontsize=8)
        fig.tight_layout(rect=(0,.06,1,.91))
        for extension in ("png", "pdf", "svg"):
            fig.savefig(output/f"{stem}.{extension}", dpi=240, bbox_inches="tight")
        plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.16, 3.6))
    for mi, (method, label, color) in enumerate(methods):
        for ti, task in enumerate(tasks):
            vals = [r.get("timing",{}).get("task_s") for r in records if r["method"]==method and r["task_id"]==task]
            vals = [v for v in vals if isinstance(v,(float,int)) and not isinstance(v,bool)]
            x = ti + (mi-.5)*.26
            if vals:
                xs=[x+(i-(len(vals)-1)/2)*.025 for i in range(len(vals))]
                ax.scatter(xs, vals, color=color, s=24, label=label if ti==0 else None)
                ax.plot([x-.07,x+.07],[statistics.mean(vals)]*2,color=color,lw=2)
                ax.annotate(f"n={len(vals)}",(x,max(vals)),xytext=(0,5),textcoords="offset points",ha="center",fontsize=8)
    ax.set(xticks=range(3),xticklabels=tasks,ylabel="Observed task time (s)")
    maximum_time=max((r.get("timing",{}).get("task_s") or 0 for r in records),default=1)
    ax.set_ylim(0,max(1,maximum_time)*1.15)
    ax.legend(frameon=False)
    fig.suptitle("Task observations and means — different timing boundaries; no speedup ratio", fontsize=11)
    save(fig,"task_times")
    fig, ax = plt.subplots(figsize=(7.16,3.3))
    for ti,task in enumerate(tasks):
        vals=[r.get("mcp_calls") for r in records if r["method"]=="codex_mcp" and r["task_id"]==task and isinstance(r.get("mcp_calls"),int)]
        if vals:
            ax.scatter([ti+(i-(len(vals)-1)/2)*.04 for i in range(len(vals))],vals,color="#0072B2")
            ax.plot([ti-.12,ti+.12],[statistics.mean(vals)]*2,color="#0072B2",lw=2)
    maximum_calls=max((r.get("mcp_calls",0) or 0 for r in records if r["method"]=="codex_mcp"),default=1)
    ax.set(xticks=range(3),xticklabels=tasks,ylabel="Recorded MCP calls per trial",ylim=(0,maximum_calls+.75))
    fig.suptitle("MCP query / action counts — GUI has no MCP calls",fontsize=11)
    save(fig,"mcp_calls")
    fig, axes = plt.subplots(1,2,figsize=(7.16,3.6),sharey=True)
    for ax,field,title in zip(axes,("first_attempt_success","final_success"),("First attempt","Final")):
        for mi,(method,label,color) in enumerate(methods):
            for ti,task in enumerate(tasks):
                vals=[r[field] for r in records if r["method"]==method and r["task_id"]==task and isinstance(r.get(field),bool)]
                if vals:
                    count=sum(vals);x=ti+(mi-.5)*.32
                    ax.bar(x,count/len(vals),width=.3,color=color,label=label if ti==0 else None)
                    ax.text(x,count/len(vals)+.025,f"{count}/{len(vals)}",ha="center",fontsize=8)
        ax.set(xticks=range(3),xticklabels=tasks,ylim=(0,1.19),title=title)
    axes[0].set_ylabel("Observed success fraction")
    handles,labels=axes[1].get_legend_handles_labels()
    fig.legend(handles,labels,loc="upper center",bbox_to_anchor=(.5,.91),ncol=2,frameon=False,fontsize=9)
    fig.suptitle("Success counts — unmeasured outcomes excluded from denominators",fontsize=11)
    save(fig,"success_counts")
    differences={}
    for before in sorted((root/"artifacts").glob("*/initial_figure.json")):
        after=before.with_name("final_figure.json")
        if after.exists():
            differences[before.parent.name]={"initial":str(before.relative_to(root)),"final":str(after.relative_to(root)),
                "differences":diff(json.loads(before.read_text(encoding="utf-8")),json.loads(after.read_text(encoding="utf-8")))}
    (root/"configuration_diffs.json").write_text(json.dumps(differences,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"charts":3,"configuration_pairs":len(differences)}))


if __name__=="__main__":
    main()

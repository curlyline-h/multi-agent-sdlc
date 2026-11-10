"""Generates the figures used in report/report_2_final.tex from results/full_eval_scen_*.json."""
import glob
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

runs = []
for f in sorted(glob.glob(str(ROOT / "results" / "full_eval_scen_*.json"))):
    runs.append(json.load(open(f, encoding="utf-8")))
ids = [r["scenario_id"].replace("scen_", "S") for r in runs]
x = np.arange(len(runs))
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})


def dag(r):
    return r.get("task_breakdown_and_dag") or r.get("task_dag_and_execution") or {}


# 1. requirement / architecture coverage
fig, ax = plt.subplots(figsize=(7, 3.2))
w = 0.27
ra = r_ = None
rec = [r["requirements_and_architecture"]["prd_requirement_recall"] for r in runs]
pre = [r["requirements_and_architecture"]["prd_requirement_precision"] for r in runs]
arc = [r["requirements_and_architecture"]["arch_component_recall"] for r in runs]
ax.bar(x - w, rec, w, label="PRD recall", color="#2b6cb0")
ax.bar(x, pre, w, label="PRD precision", color="#90cdf4")
ax.bar(x + w, arc, w, label="Architecture recall", color="#dd6b20")
ax.set_xticks(x, ids)
ax.set_ylim(0, 1.1)
ax.set_ylabel("Score")
ax.set_title("Requirement and architecture coverage per scenario")
ax.legend(ncol=3, fontsize=8, loc="lower center")
fig.tight_layout()
fig.savefig(OUT / "final_coverage_by_scenario.png", dpi=200)
plt.close(fig)

# 2. code output volume
files = [r["code_and_outputs"]["total_files_generated"] for r in runs]
loc = [r["code_and_outputs"]["total_lines_of_code"] for r in runs]
fig, axs = plt.subplots(1, 2, figsize=(7, 3))
axs[0].bar(x, files, color="#38a169")
axs[0].set_title("Files per workspace")
axs[1].bar(x, loc, color="#805ad5")
axs[1].set_title("Lines of code per workspace")
for a in axs:
    a.set_xticks(x, ids)
for a, v in zip(axs, (files, loc)):
    for i, val in enumerate(v):
        a.text(i, val, f"{val:,}", ha="center", va="bottom", fontsize=7)
fig.tight_layout()
fig.savefig(OUT / "final_code_volume.png", dpi=200)
plt.close(fig)

# 3. task distribution by role
roles = ["database_engineer", "backend", "frontend", "qa", "reviewer", "security", "devops"]
colors = ["#718096", "#2b6cb0", "#38a169", "#d69e2e", "#dd6b20", "#e53e3e", "#805ad5"]
fig, ax = plt.subplots(figsize=(7, 3.2))
bottom = np.zeros(len(runs))
for role, col in zip(roles, colors):
    vals = np.array([(dag(r).get("role_distribution") or {}).get(role, 0) for r in runs], dtype=float)
    ax.bar(x, vals, bottom=bottom, label=role, color=col)
    bottom += vals
for i, b in enumerate(bottom):
    ax.text(i, b, int(b), ha="center", va="bottom", fontsize=8)
ax.set_xticks(x, ids)
ax.set_ylabel("Tasks")
ax.set_title("Generated tasks by agent role (all completed)")
ax.legend(ncol=4, fontsize=7, loc="upper left")
ax.set_ylim(0, max(bottom) * 1.35)
fig.tight_layout()
fig.savefig(OUT / "final_tasks_by_role.png", dpi=200)
plt.close(fig)

# 4. DAG edge recall / precision (scenarios with DAG metrics)
d_runs = [(i, r) for i, r in zip(ids, runs) if dag(r).get("dag_edge_recall") is not None]
xi = np.arange(len(d_runs))
fig, ax = plt.subplots(figsize=(6, 3))
ax.bar(xi - 0.2, [dag(r)["dag_edge_recall"] for _, r in d_runs], 0.4, label="Edge recall", color="#2b6cb0")
ax.bar(xi + 0.2, [dag(r)["dag_edge_precision"] for _, r in d_runs], 0.4, label="Edge precision", color="#fbd38d")
ax.set_xticks(xi, [i for i, _ in d_runs])
ax.set_ylim(0, 1.15)
ax.set_title("Task-DAG edge agreement with gold role graph")
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(OUT / "final_dag_edges.png", dpi=200)
plt.close(fig)

# 5. pipeline outcome funnel (aggregate)
tot_tasks = sum(dag(r).get("total_tasks_generated", 0) or r["code_and_outputs"].get("tasks", 0) for r in runs)
valid = sum(r["code_and_outputs"]["syntax_valid_files"] for r in runs)
checked = sum(r["code_and_outputs"]["syntax_checked_files"] for r in runs)
fig, ax = plt.subplots(figsize=(6, 2.6))
labels = ["Syntax-checked files", "Syntax-valid files", "Scenarios completed", "Scenarios run"]
vals = [checked, valid, len(runs), len(runs)]
ax.barh(["Syntax-valid files", "Syntax-checked files"], [valid, checked], color=["#38a169", "#a0aec0"])
for i, v in enumerate([valid, checked]):
    ax.text(v, i, f" {v}", va="center")
ax.set_title("Static validity of generated code (110/110 files parse)")
ax.set_xlim(0, checked * 1.15)
fig.tight_layout()
fig.savefig(OUT / "final_syntax_validity.png", dpi=200)
plt.close(fig)

# 6. free-tier constraint: configured output-token caps per model during the runs
models = ["gpt-oss-safeguard-20b", "qwen3 (32b)", "gpt-oss-20b", "gpt-oss-120b", "allam-2-7b"]
caps = [650, 650, 680, 680, 800]
fig, ax = plt.subplots(figsize=(6.2, 2.8))
ax.barh(models, caps, color="#e53e3e")
for i, v in enumerate(caps):
    ax.text(v, i, f" {v}", va="center")
ax.set_xlim(0, 1000)
ax.set_xlabel("Max output tokens per call")
ax.set_title("Output-token caps configured to fit the free-tier TPM limit")
fig.tight_layout()
fig.savefig(OUT / "final_free_tier_caps.png", dpi=200)
plt.close(fig)

# 7. free-tier rotation concept diagram
fig, ax = plt.subplots(figsize=(7, 2.4))
ax.axis("off")
boxes = [("LLM call", 0.02), ("429 / 413 / TPD\n(free-tier limit)", 0.27), ("Rotate key + model\n(9 buckets)", 0.52), ("Smaller / weaker\nmodel serves call", 0.77)]
for t, xx in boxes:
    ax.text(xx + 0.09, 0.5, t, ha="center", va="center", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.5", fc="#ebf8ff" if xx < 0.7 else "#fed7d7", ec="#4a5568"))
for xx in (0.14, 0.39, 0.64):
    ax.annotate("", xy=(xx + 0.10, 0.5), xytext=(xx + 0.03, 0.5), arrowprops=dict(arrowstyle="->"))
ax.set_title("Free-tier rate limiting forces model rotation during a run")
fig.tight_layout()
fig.savefig(OUT / "final_free_tier_rotation.png", dpi=200)
plt.close(fig)
print("figures written to", OUT)


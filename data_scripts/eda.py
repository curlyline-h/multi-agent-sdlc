"""
Exploratory Data Analysis (EDA) Charts for the Multi-Agent SDLC Benchmark.

Reads `data/processed/benchmark.json` and generates four publication-ready PNG figures
in `reports/figures/`:
  1. `category_source_distribution.png` — Scenarios per category broken down by source (manual vs github)
  2. `requirement_length_distribution.png` — Requirement character-length distribution and IQR bounds
  3. `tasks_by_agent_role.png` — Task distribution across specialized SDLC agent roles
  4. `dependency_depth_distribution.png` — Task DAG dependency depth per category
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from data_scripts.features import compute_dag_depth

ROOT_DIR = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT_DIR / "data" / "processed" / "benchmark.json"
FIGURES_DIR = ROOT_DIR / "reports" / "figures"


def generate_eda_charts(
    benchmark_path: Path = BENCHMARK_PATH,
    figures_dir: Path = FIGURES_DIR,
) -> List[Path]:
    """Generate all four EDA plots in `reports/figures/`."""
    with open(benchmark_path, "r", encoding="utf-8") as f:
        scenarios: List[Dict[str, Any]] = json.load(f)

    figures_dir.mkdir(parents=True, exist_ok=True)
    saved_paths: List[Path] = []

    categories = ["crud", "rest_api", "ecommerce", "auth", "db_app"]

    # 1. Category & Source Distribution
    manual_counts = [
        sum(1 for s in scenarios if s["category"] == c and s["source"] == "manual")
        for c in categories
    ]
    github_counts = [
        sum(1 for s in scenarios if s["category"] == c and s["source"] == "github")
        for c in categories
    ]

    x = np.arange(len(categories))
    width = 0.36
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=180)
    ax.bar(x - width / 2, manual_counts, width, label="Manual (25)", color="#2563eb")
    ax.bar(x + width / 2, github_counts, width, label="GitHub Issues (15)", color="#10b981")
    ax.set_title("Benchmark Scenarios by Application Category & Source", fontsize=12, fontweight="bold")
    ax.set_xlabel("Application Category")
    ax.set_ylabel("Number of Scenarios")
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylim(0, max(manual_counts + github_counts) + 2)
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    p1 = figures_dir / "category_source_distribution.png"
    fig.savefig(p1)
    plt.close(fig)
    saved_paths.append(p1)

    # 2. Requirement Length Distribution
    lengths = [len(s["requirement"]) for s in scenarios]
    q1, q3 = np.percentile(lengths, [25, 75])
    iqr = q3 - q1
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=180)
    ax.hist(lengths, bins=10, color="#6366f1", edgecolor="white", alpha=0.85)
    ax.axvline(float(np.mean(lengths)), color="#ef4444", linestyle="--", linewidth=1.8, label=f"Mean ({np.mean(lengths):.0f} chars)")
    ax.axvline(float(q1 - 1.5 * iqr), color="#f59e0b", linestyle=":", linewidth=1.5, label="1.5x IQR Bounds")
    ax.axvline(float(q3 + 1.5 * iqr), color="#f59e0b", linestyle=":", linewidth=1.5)
    ax.set_title("Requirement Prompt Length Distribution (Characters)", fontsize=12, fontweight="bold")
    ax.set_xlabel("Requirement Length (Characters)")
    ax.set_ylabel("Scenario Count")
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    fig.tight_layout()
    p2 = figures_dir / "requirement_length_distribution.png"
    fig.savefig(p2)
    plt.close(fig)
    saved_paths.append(p2)

    # 3. Tasks by Agent Role
    role_counter: Counter[str] = Counter()
    for s in scenarios:
        for t in s.get("tasks", []):
            role_counter[t.get("role", "backend")] += 1
    roles = [r for r, _ in role_counter.most_common()]
    counts = [role_counter[r] for r in roles]
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=180)
    ax.barh(roles[::-1], counts[::-1], color="#0ea5e9")
    ax.set_title("Expected Ground-Truth Tasks Across SDLC Agent Roles", fontsize=12, fontweight="bold")
    ax.set_xlabel("Total Tasks Across 40 Benchmark Scenarios")
    ax.set_ylabel("Assigned Agent Role")
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    fig.tight_layout()
    p3 = figures_dir / "tasks_by_agent_role.png"
    fig.savefig(p3)
    plt.close(fig)
    saved_paths.append(p3)

    # 4. Dependency Depth by Category
    depth_by_cat: Dict[str, List[int]] = defaultdict(list)
    for s in scenarios:
        depth_by_cat[s["category"]].append(compute_dag_depth(s.get("tasks", [])))
    avg_depths = [float(np.mean(depth_by_cat[c])) for c in categories]
    avg_tasks = [
        float(np.mean([len(s.get("tasks", [])) for s in scenarios if s["category"] == c]))
        for c in categories
    ]
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=180)
    ax.plot(categories, avg_tasks, marker="o", linewidth=2.2, color="#2563eb", label="Avg Tasks per Scenario")
    ax.plot(categories, avg_depths, marker="s", linewidth=2.2, color="#ec4899", label="Avg DAG Dependency Depth")
    ax.set_title("Task Count & Dependency Chain Depth by Category", fontsize=12, fontweight="bold")
    ax.set_xlabel("Application Category")
    ax.set_ylabel("Count / Depth")
    ax.set_ylim(0, max(avg_tasks) + 1.5)
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()
    p4 = figures_dir / "dependency_depth_distribution.png"
    fig.savefig(p4)
    plt.close(fig)
    saved_paths.append(p4)

    print(f"[eda] Generated {len(saved_paths)} EDA figures in {figures_dir}")
    return saved_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate EDA figures for SDLC benchmark.")
    parser.add_argument("--input", type=Path, default=BENCHMARK_PATH)
    parser.add_argument("--output-dir", type=Path, default=FIGURES_DIR)
    args = parser.parse_args()
    generate_eda_charts(args.input, args.output_dir)


if __name__ == "__main__":
    main()


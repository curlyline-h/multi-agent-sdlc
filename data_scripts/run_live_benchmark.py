"""
Live Empirical Benchmark Runner for Multi-Agent SDLC Platform.
Executes both the live single-agent baseline and the live 4-stage multi-agent pipeline
(Product Manager -> System Architect -> Task Breakdown -> Security Auditor)
against the 6 holdout test scenarios using the configured Groq LLM.
Computes real Precision, Recall, F1, AUC-ROC, latency, tokens, and cost.
Exports actual empirical CSV and JSON results to results/live_*.
"""
import os
import sys
import json
import time
import re
from pathlib import Path
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

from agents.src.shared.llm import get_llm
from agents.src.agents.task_breakdown.nodes import generate_tasks_node
from agents.src.agents.task_breakdown.state import TaskBreakdownState
from agents.src.evaluation.single_agent_baseline import run_single_agent_baseline
from agents.src.evaluation.metrics import (
    compute_requirement_coverage_metrics,
    compute_dependency_dag_metrics,
    compute_security_finding_metrics,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
TEST_SPLIT_PATH = ROOT_DIR / "data" / "splits" / "test.json"
RESULTS_DIR = ROOT_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def run_live_multi_agent(scenario: Dict[str, Any], llm) -> Dict[str, Any]:
    """Executes live multi-agent pipeline across PM, Architect, Task Breakdown, and Security."""
    start_time = time.time()
    req_text = scenario["requirement"]
    total_tokens = 0

    # 1. Product Manager Agent -> PRD
    pm_prompt = (
        "You are a Lead Product Manager. Write a structured Product Requirements Document (PRD) for the following project:\n"
        f"Requirement: {req_text}\n\n"
        "Include:\n1. Executive Summary\n2. Functional Requirements (clear bullet list)\n3. Non-Functional Requirements"
    )
    pm_res = llm.invoke(pm_prompt)
    prd_text = pm_res.content if hasattr(pm_res, "content") else str(pm_res)
    total_tokens += len(prd_text.split()) * 2

    # Extract functional requirements from PRD text
    gen_reqs = []
    for line in prd_text.split("\n"):
        line_s = line.strip()
        if (line_s.startswith("- ") or line_s.startswith("* ") or re.match(r"^\d+\.", line_s)) and len(line_s) > 10:
            cleaned = re.sub(r"^[-*\d.]+\s*", "", line_s)
            gen_reqs.append(cleaned)
    if not gen_reqs:
        gen_reqs = [prd_text[:200]]

    # 2. System Architect Agent -> Architecture Specification
    arch_prompt = (
        "You are a Principal Software Architect. Given this PRD, produce a technical design specification:\n"
        f"PRD:\n{prd_text[:3000]}\n\n"
        "Specify:\n1. System Architecture Components\n2. Database Schemas\n3. REST API Routes"
    )
    arch_res = llm.invoke(arch_prompt)
    arch_text = arch_res.content if hasattr(arch_res, "content") else str(arch_res)
    total_tokens += len(arch_text.split()) * 2

    # 3. Task Breakdown Agent -> Task DAG
    tb_state = TaskBreakdownState(
        prd=prd_text[:3000],
        final_design_doc=arch_text[:3000],
        workflow_tasks=[]
    )
    tb_out = generate_tasks_node(tb_state)
    raw_tasks = tb_out.get("workflow_tasks", [])
    total_tokens += sum(len(str(t).split()) for t in raw_tasks) * 2

    # Standardize tasks for metric evaluation
    gen_tasks = []
    for t in raw_tasks:
        if isinstance(t, dict):
            gen_tasks.append({
                "title": t.get("title", "Task"),
                "role": t.get("assignee_role") or t.get("role") or "backend",
                "depends_on": t.get("dependencies") or t.get("depends_on") or []
            })

    # 4. Security Agent -> Vulnerability Audit
    sec_prompt = (
        "You are a Senior Security Engineer. Audit this specification and architecture for OWASP security vulnerabilities and CWEs:\n"
        f"PRD: {prd_text[:2000]}\nArchitecture: {arch_text[:2000]}\n\n"
        "Respond with a raw JSON list:\n"
        '[{"title": "string", "severity": "CRITICAL|HIGH|MEDIUM|LOW", "mitigation": "string", "description": "string"}]\n'
        "Respond ONLY with valid JSON."
    )
    sec_res = llm.invoke(sec_prompt)
    sec_text = sec_res.content if hasattr(sec_res, "content") else str(sec_res)
    total_tokens += len(sec_text.split()) * 2

    match = re.search(r"\[.*\]", sec_text, re.DOTALL)
    if match:
        try:
            findings = json.loads(match.group(0))
        except Exception:
            findings = []
    else:
        findings = []

    elapsed = round(time.time() - start_time, 2)
    cost = round(total_tokens * 0.0000008, 5)

    return {
        "scenario_id": scenario["id"],
        "functional_requirements": gen_reqs,
        "tasks": gen_tasks,
        "security_findings": findings,
        "latency_seconds": elapsed,
        "estimated_tokens": total_tokens,
        "estimated_cost_usd": cost,
    }

def main():
    print("=================================================================")
    print("STARTING LIVE EMPIRICAL EVALUATION ON HOLDOUT TEST SPLIT (N=6)")
    print("=================================================================")
    
    with open(TEST_SPLIT_PATH, "r", encoding="utf-8") as f:
        scenarios: List[Dict[str, Any]] = json.load(f)

    llm = get_llm(temperature=0.1, max_tokens=3500)
    
    comparison_rows = []

    for idx, scen in enumerate(scenarios):
        scen_id = scen["id"]
        cat = scen["category"]
        gt_reqs = scen.get("expected_functional_reqs", [])
        gt_tasks = scen.get("tasks", [])
        gt_sec = scen.get("security_reqs", [])

        print(f"\n[{idx+1}/{len(scenarios)}] Running Scenario: {scen_id} (Category: {cat})...")

        # 1. Live Single-Agent Baseline Run
        print("  -> Executing Live Single-Agent Baseline...")
        b_out = run_single_agent_baseline(scen, llm=llm)
        b_req_m = compute_requirement_coverage_metrics(b_out.get("functional_requirements", []), gt_reqs)
        b_dag_m = compute_dependency_dag_metrics(b_out.get("tasks", []), gt_tasks)
        b_sec_m = compute_security_finding_metrics(b_out.get("security_findings", []), gt_sec)
        print(f"     Baseline F1: Req={b_req_m['f1']:.3f}, DAG={b_dag_m['dag_f1']:.3f}, Sec={b_sec_m['security_f1']:.3f}, Latency={b_out['latency_seconds']}s")

        # 2. Live Multi-Agent Orchestration Run
        print("  -> Executing Live Multi-Agent Pipeline (PM -> Architect -> Task Breakdown -> Security)...")
        m_out = run_live_multi_agent(scen, llm)
        m_req_m = compute_requirement_coverage_metrics(m_out.get("functional_requirements", []), gt_reqs)
        m_dag_m = compute_dependency_dag_metrics(m_out.get("tasks", []), gt_tasks)
        m_sec_m = compute_security_finding_metrics(m_out.get("security_findings", []), gt_sec)
        print(f"     Multi-Agent F1: Req={m_req_m['f1']:.3f}, DAG={m_dag_m['dag_f1']:.3f}, Sec={m_sec_m['security_f1']:.3f}, Latency={m_out['latency_seconds']}s")

        comparison_rows.append({
            "scenario_id": scen_id,
            "category": cat,
            "baseline_req_p": b_req_m["precision"],
            "baseline_req_r": b_req_m["recall"],
            "baseline_req_f1": b_req_m["f1"],
            "multi_req_p": m_req_m["precision"],
            "multi_req_r": m_req_m["recall"],
            "multi_req_f1": m_req_m["f1"],
            "baseline_dag_f1": b_dag_m["dag_f1"],
            "multi_dag_f1": m_dag_m["dag_f1"],
            "baseline_sec_f1": b_sec_m["security_f1"],
            "multi_sec_f1": m_sec_m["security_f1"],
            "baseline_auc_roc": b_sec_m["auc_roc"],
            "multi_auc_roc": m_sec_m["auc_roc"],
            "baseline_latency_s": b_out.get("latency_seconds", 0),
            "multi_latency_s": m_out.get("latency_seconds", 0),
            "baseline_tokens": b_out.get("estimated_tokens", 0),
            "multi_tokens": m_out.get("estimated_tokens", 0),
            "baseline_cost_usd": b_out.get("estimated_cost_usd", 0),
            "multi_cost_usd": m_out.get("estimated_cost_usd", 0),
        })

    # Save to CSV
    csv_path = RESULTS_DIR / "live_benchmark_comparison.csv"
    import csv
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparison_rows[0].keys()))
        writer.writeheader()
        writer.writerows(comparison_rows)
    print(f"\n[OK] Saved live comparison to {csv_path}")

    # Compute per-category averages
    from collections import defaultdict
    cat_stats = defaultdict(lambda: {"baseline_req_f1": [], "multi_req_f1": [], "baseline_dag_f1": [], "multi_dag_f1": [], "multi_auc": []})
    for r in comparison_rows:
        c = r["category"]
        cat_stats[c]["baseline_req_f1"].append(r["baseline_req_f1"])
        cat_stats[c]["multi_req_f1"].append(r["multi_req_f1"])
        cat_stats[c]["baseline_dag_f1"].append(r["baseline_dag_f1"])
        cat_stats[c]["multi_dag_f1"].append(r["multi_dag_f1"])
        cat_stats[c]["multi_auc"].append(r["multi_auc_roc"])

    summary_rows = []
    for cat, data in sorted(cat_stats.items()):
        summary_rows.append({
            "category": cat,
            "sample_count": len(data["multi_req_f1"]),
            "mean_baseline_req_f1": round(sum(data["baseline_req_f1"])/len(data["baseline_req_f1"]), 4),
            "mean_multi_req_f1": round(sum(data["multi_req_f1"])/len(data["multi_req_f1"]), 4),
            "mean_baseline_dag_f1": round(sum(data["baseline_dag_f1"])/len(data["baseline_dag_f1"]), 4),
            "mean_multi_dag_f1": round(sum(data["multi_dag_f1"])/len(data["multi_dag_f1"]), 4),
            "mean_multi_auc_roc": round(sum(data["multi_auc"])/len(data["multi_auc"]), 4),
        })

    summary_path = RESULTS_DIR / "live_category_summary.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"[OK] Saved category summary to {summary_path}")

    # Compute overall macro averages
    all_b_req = [r["baseline_req_f1"] for r in comparison_rows]
    all_m_req = [r["multi_req_f1"] for r in comparison_rows]
    all_b_dag = [r["baseline_dag_f1"] for r in comparison_rows]
    all_m_dag = [r["multi_dag_f1"] for r in comparison_rows]
    all_b_sec = [r["baseline_sec_f1"] for r in comparison_rows]
    all_m_sec = [r["multi_sec_f1"] for r in comparison_rows]
    all_b_auc = [r["baseline_auc_roc"] for r in comparison_rows]
    all_m_auc = [r["multi_auc_roc"] for r in comparison_rows]

    overall_metrics = {
        "baseline_overall_req_f1": round(sum(all_b_req)/len(all_b_req), 4),
        "multi_overall_req_f1": round(sum(all_m_req)/len(all_m_req), 4),
        "baseline_overall_dag_f1": round(sum(all_b_dag)/len(all_b_dag), 4),
        "multi_overall_dag_f1": round(sum(all_m_dag)/len(all_m_dag), 4),
        "baseline_overall_sec_f1": round(sum(all_b_sec)/len(all_b_sec), 4),
        "multi_overall_sec_f1": round(sum(all_m_sec)/len(all_m_sec), 4),
        "baseline_overall_auc_roc": round(sum(all_b_auc)/len(all_b_auc), 4),
        "multi_overall_auc_roc": round(sum(all_m_auc)/len(all_m_auc), 4),
        "relative_improvement_req_f1": round((sum(all_m_req) - sum(all_b_req)) / sum(all_b_req) * 100, 2),
        "relative_improvement_dag_f1": round((sum(all_m_dag) - sum(all_b_dag)) / (sum(all_b_dag) or 1) * 100, 2),
    }

    report_path = RESULTS_DIR / "live_error_analysis_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "overall_status": "LIVE_EVALUATION_PASS",
            "overall_metrics": overall_metrics,
            "category_summary": summary_rows,
            "individual_comparisons": comparison_rows
        }, f, indent=2)
    print(f"[OK] Saved live error analysis report to {report_path}")

    print("\n================== LIVE EMPIRICAL SUMMARY ==================")
    for k, v in overall_metrics.items():
        print(f"  {k}: {v}")
    print("============================================================")

if __name__ == "__main__":
    main()


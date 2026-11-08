"""
Unit Tests for Evaluation Metrics (Requirement Coverage, DAG Edges, Security Findings).
"""

from __future__ import annotations

import pytest

from agents.src.evaluation.metrics import (
    compute_dependency_dag_metrics,
    compute_requirement_coverage_metrics,
    compute_security_finding_metrics,
)


def test_requirement_coverage_metrics():
    ground_truth = [
        "Create, read, update, and soft-delete employee profiles",
        "Support CSV bulk import with row-level validation reporting",
        "Provide cursor-based pagination and filter by department",
    ]
    generated_good = [
        "Create, read, update, and soft delete employee records",
        "Support CSV bulk import with row validation",
        "Provide pagination and filter by department",
    ]
    metrics = compute_requirement_coverage_metrics(generated_good, ground_truth)
    assert metrics["precision"] > 0.8
    assert metrics["recall"] > 0.8
    assert metrics["f1"] > 0.8
    assert metrics["true_positives"] == 3


def test_requirement_coverage_empty_or_poor_match():
    ground_truth = ["Implement multi-factor authentication with TOTP"]
    generated_unrelated = ["Build a blue button on the header"]
    metrics = compute_requirement_coverage_metrics(generated_unrelated, ground_truth)
    assert metrics["true_positives"] == 0
    assert metrics["f1"] == 0.0


def test_dependency_dag_metrics():
    gt_tasks = [
        {"title": "Schema design", "role": "database_engineer", "depends_on": []},
        {"title": "REST API", "role": "backend", "depends_on": ["Schema design"]},
        {"title": "Frontend UI", "role": "frontend", "depends_on": ["REST API"]},
    ]
    gen_tasks = [
        {"title": "Create tables", "role": "database_engineer", "depends_on": []},
        {"title": "Build endpoints", "role": "backend", "depends_on": ["Create tables"]},
        {"title": "Create views", "role": "frontend", "depends_on": ["Build endpoints"]},
    ]
    metrics = compute_dependency_dag_metrics(gen_tasks, gt_tasks)
    assert metrics["dag_precision"] == 1.0
    assert metrics["dag_recall"] == 1.0
    assert metrics["dag_f1"] == 1.0


def test_security_finding_metrics():
    gt_security = [
        "Sanitize CSV cell values against formula injection (=, +, -, @ prefixes)",
        "Enforce role-based access control so only HR admins can mutate records",
    ]
    detected = [
        {"title": "CSV formula injection vulnerability", "severity": "HIGH", "mitigation": "Sanitize formula prefixes"},
        {"title": "Broken role access control", "severity": "CRITICAL", "mitigation": "Enforce HR admin RBAC check"},
    ]
    metrics = compute_security_finding_metrics(detected, gt_security)
    assert metrics["security_precision"] == 1.0
    assert metrics["security_recall"] == 1.0
    assert metrics["security_f1"] == 1.0
    assert metrics["auc_roc"] >= 0.8


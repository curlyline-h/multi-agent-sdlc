"""
Unit Tests for Processed SDLC Benchmark Dataset Schema and Stratified Splits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[3]
BENCHMARK_PATH = ROOT_DIR / "data" / "processed" / "benchmark.json"
SPLITS_DIR = ROOT_DIR / "data" / "splits"

REQUIRED_KEYS = {
    "id",
    "category",
    "source",
    "requirement",
    "expected_functional_reqs",
    "expected_components",
    "tasks",
    "acceptance_criteria",
    "security_reqs",
    "test_cases",
}

VALID_CATEGORIES = {"crud", "rest_api", "ecommerce", "auth", "db_app"}
VALID_SOURCES = {"manual", "github"}


@pytest.fixture(scope="module")
def benchmark_data():
    assert BENCHMARK_PATH.exists(), f"Missing processed benchmark at {BENCHMARK_PATH}"
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_benchmark_scenario_count_and_unique_ids(benchmark_data):
    assert len(benchmark_data) == 40
    ids = [s["id"] for s in benchmark_data]
    assert len(ids) == len(set(ids)), "Scenario IDs must be unique"


def test_benchmark_schema_keys_and_types(benchmark_data):
    for scenario in benchmark_data:
        missing = REQUIRED_KEYS - set(scenario.keys())
        assert not missing, f"Scenario {scenario.get('id')} missing keys: {missing}"
        assert scenario["category"] in VALID_CATEGORIES
        assert scenario["source"] in VALID_SOURCES
        assert isinstance(scenario["requirement"], str) and len(scenario["requirement"]) >= 50
        assert len(scenario["expected_functional_reqs"]) >= 2
        assert len(scenario["expected_components"]) >= 2
        assert len(scenario["acceptance_criteria"]) >= 2
        assert len(scenario["security_reqs"]) >= 1
        assert len(scenario["test_cases"]) >= 2


def test_task_dag_validity(benchmark_data):
    for scenario in benchmark_data:
        tasks = scenario["tasks"]
        assert len(tasks) >= 3, f"Scenario {scenario['id']} must have at least 3 tasks"
        titles = {t["title"] for t in tasks}
        for t in tasks:
            assert "title" in t and "role" in t and "depends_on" in t
            for dep in t["depends_on"]:
                assert dep in titles, f"Task '{t['title']}' depends on unknown task '{dep}'"
                assert dep != t["title"], f"Task '{t['title']}' cannot depend on itself"


def test_source_and_category_balance(benchmark_data):
    manual_count = sum(1 for s in benchmark_data if s["source"] == "manual")
    github_count = sum(1 for s in benchmark_data if s["source"] == "github")
    assert manual_count == 25
    assert github_count == 15
    for cat in VALID_CATEGORIES:
        cat_count = sum(1 for s in benchmark_data if s["category"] == cat)
        assert cat_count == 8, f"Expected 8 scenarios for category {cat}, got {cat_count}"


def test_stratified_splits_exist_and_partition_cleanly():
    dev_path = SPLITS_DIR / "dev.json"
    val_path = SPLITS_DIR / "val.json"
    test_path = SPLITS_DIR / "test.json"
    assert dev_path.exists() and val_path.exists() and test_path.exists()

    dev = json.loads(dev_path.read_text(encoding="utf-8"))
    val = json.loads(val_path.read_text(encoding="utf-8"))
    test = json.loads(test_path.read_text(encoding="utf-8"))

    assert len(dev) == 28
    assert len(val) == 6
    assert len(test) == 6

    dev_ids = {s["id"] for s in dev}
    val_ids = {s["id"] for s in val}
    test_ids = {s["id"] for s in test}
    assert dev_ids.isdisjoint(val_ids)
    assert dev_ids.isdisjoint(test_ids)
    assert val_ids.isdisjoint(test_ids)
    assert len(dev_ids | val_ids | test_ids) == 40


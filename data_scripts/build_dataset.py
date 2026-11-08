"""
Dataset Builder Merging Manual and GitHub Benchmark Scenarios.

Loads hand-written benchmark scenarios (`data/raw/scenarios_manual.json`) and
GitHub feature-request scenarios (`data/raw/github_issues.json`), validates
their canonical keys, and merges them into a unified raw dataset ready for
cleaning (`data/raw/merged_scenarios.json`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
MANUAL_PATH = ROOT_DIR / "data" / "raw" / "scenarios_manual.json"
GITHUB_PATH = ROOT_DIR / "data" / "raw" / "github_issues.json"
MERGED_RAW_PATH = ROOT_DIR / "data" / "raw" / "merged_scenarios.json"

REQUIRED_KEYS = (
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
)

VALID_CATEGORIES = {"crud", "rest_api", "ecommerce", "auth", "db_app"}
VALID_SOURCES = {"manual", "github"}


def normalize_scenario_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw scenario dictionary to the canonical benchmark schema."""
    tasks = []
    for t in raw.get("tasks", []):
        if isinstance(t, dict):
            tasks.append(
                {
                    "title": str(t.get("title", "")).strip(),
                    "role": str(t.get("role", "backend")).strip(),
                    "depends_on": list(t.get("depends_on", [])),
                }
            )
    return {
        "id": str(raw.get("id", "")).strip(),
        "category": str(raw.get("category", "")).strip().lower(),
        "source": str(raw.get("source", "")).strip().lower(),
        "requirement": str(raw.get("requirement", "")).strip(),
        "expected_functional_reqs": [
            str(x).strip() for x in raw.get("expected_functional_reqs", []) if str(x).strip()
        ],
        "expected_components": [
            str(x).strip() for x in raw.get("expected_components", []) if str(x).strip()
        ],
        "tasks": tasks,
        "acceptance_criteria": [
            str(x).strip() for x in raw.get("acceptance_criteria", []) if str(x).strip()
        ],
        "security_reqs": [
            str(x).strip() for x in raw.get("security_reqs", []) if str(x).strip()
        ],
        "test_cases": [
            str(x).strip() for x in raw.get("test_cases", []) if str(x).strip()
        ],
    }


def build_merged_dataset(
    manual_path: Path = MANUAL_PATH,
    github_path: Path = GITHUB_PATH,
    output_path: Path = MERGED_RAW_PATH,
) -> List[Dict[str, Any]]:
    """Merge manual and GitHub scenario collections in deterministic ID order."""
    if not manual_path.exists():
        raise FileNotFoundError(f"Manual scenarios file not found: {manual_path}")
    if not github_path.exists():
        raise FileNotFoundError(f"GitHub scenarios file not found: {github_path}")

    with open(manual_path, "r", encoding="utf-8") as f:
        manual_scenarios = json.load(f)
    with open(github_path, "r", encoding="utf-8") as f:
        github_scenarios = json.load(f)

    merged: List[Dict[str, Any]] = []
    for raw in list(manual_scenarios) + list(github_scenarios):
        normalized = normalize_scenario_record(raw)
        if normalized["category"] not in VALID_CATEGORIES:
            raise ValueError(
                f"Scenario {normalized['id']} has invalid category: {normalized['category']}"
            )
        if normalized["source"] not in VALID_SOURCES:
            raise ValueError(
                f"Scenario {normalized['id']} has invalid source: {normalized['source']}"
            )
        merged.append(normalized)

    merged.sort(key=lambda item: item["id"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)

    print(
        f"[build_dataset] Merged {len(manual_scenarios)} manual + "
        f"{len(github_scenarios)} github = {len(merged)} total scenarios -> {output_path}"
    )
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge manual and GitHub benchmark scenarios."
    )
    parser.add_argument("--manual", type=Path, default=MANUAL_PATH)
    parser.add_argument("--github", type=Path, default=GITHUB_PATH)
    parser.add_argument("--output", type=Path, default=MERGED_RAW_PATH)
    args = parser.parse_args()
    build_merged_dataset(args.manual, args.github, args.output)


if __name__ == "__main__":
    main()


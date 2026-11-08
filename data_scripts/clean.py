"""
Dataset Cleaning for Missing Fields, Duplicates, and Requirement Length Outliers.

Reads the merged scenario dataset (`data/raw/merged_scenarios.json` or falls back
to combining `scenarios_manual.json` and `github_issues.json`), drops or fills
empty keys, deduplicates by normalized requirement text, flags requirements outside
the `1.5 * IQR` character-length fence, validates task dependency references, and
writes the final 40-scenario benchmark to `data/processed/benchmark.json`.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

ROOT_DIR = Path(__file__).resolve().parents[1]
MERGED_RAW_PATH = ROOT_DIR / "data" / "raw" / "merged_scenarios.json"
PROCESSED_PATH = ROOT_DIR / "data" / "processed" / "benchmark.json"

LIST_KEYS = (
    "expected_functional_reqs",
    "expected_components",
    "tasks",
    "acceptance_criteria",
    "security_reqs",
    "test_cases",
)


def normalize_text_for_dedup(text: str) -> str:
    """Lowercase and collapse whitespace/punctuation for exact/near duplicate detection."""
    cleaned = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def compute_iqr_bounds(lengths: List[int]) -> Tuple[float, float]:
    """Compute [Q1 - 1.5 * IQR, Q3 + 1.5 * IQR] Tukey outlier fences."""
    if not lengths:
        return (0.0, 0.0)
    arr = np.asarray(lengths, dtype=float)
    q1 = float(np.percentile(arr, 25))
    q3 = float(np.percentile(arr, 75))
    iqr = q3 - q1
    return (q1 - 1.5 * iqr, q3 + 1.5 * iqr)


def fill_or_validate_record(record: Dict[str, Any]) -> Dict[str, Any] | None:
    """Drop records missing core identifiers/requirement; fill optional empty list keys."""
    scen_id = str(record.get("id", "")).strip()
    requirement = str(record.get("requirement", "")).strip()
    category = str(record.get("category", "")).strip().lower()
    source = str(record.get("source", "manual")).strip().lower()

    if not scen_id or not requirement or not category:
        return None

    cleaned = dict(record)
    cleaned["id"] = scen_id
    cleaned["category"] = category
    cleaned["source"] = source
    cleaned["requirement"] = requirement

    for key in LIST_KEYS:
        val = cleaned.get(key)
        if not isinstance(val, list):
            cleaned[key] = []

    # Clean task dependencies so every depends_on entry references a valid task title in the scenario
    valid_titles = {
        str(t.get("title", "")).strip()
        for t in cleaned["tasks"]
        if isinstance(t, dict) and str(t.get("title", "")).strip()
    }
    normalized_tasks = []
    for t in cleaned["tasks"]:
        if not isinstance(t, dict):
            continue
        title = str(t.get("title", "")).strip()
        if not title:
            continue
        role = str(t.get("role", "backend")).strip() or "backend"
        deps = [
            str(d).strip()
            for d in t.get("depends_on", [])
            if str(d).strip() in valid_titles and str(d).strip() != title
        ]
        normalized_tasks.append({"title": title, "role": role, "depends_on": deps})
    cleaned["tasks"] = normalized_tasks

    if not cleaned["expected_components"]:
        cleaned["expected_components"] = ["database_schema", "backend_api", "frontend_ui"]
    if not cleaned["security_reqs"]:
        cleaned["security_reqs"] = [
            "Enforce authentication, authorization, and strict input validation"
        ]

    return cleaned


def clean_dataset(
    input_path: Path = MERGED_RAW_PATH,
    output_path: Path = PROCESSED_PATH,
) -> List[Dict[str, Any]]:
    """Run full cleaning pipeline and write `data/processed/benchmark.json`."""
    if not input_path.exists():
        from data_scripts.build_dataset import build_merged_dataset

        raw_records = build_merged_dataset(output_path=input_path)
    else:
        with open(input_path, "r", encoding="utf-8") as f:
            raw_records = json.load(f)

    deduped: List[Dict[str, Any]] = []
    seen_texts: set[str] = set()
    seen_ids: set[str] = set()

    for item in raw_records:
        filled = fill_or_validate_record(item)
        if filled is None:
            continue
        norm_req = normalize_text_for_dedup(filled["requirement"])
        if norm_req in seen_texts or filled["id"] in seen_ids:
            continue
        seen_texts.add(norm_req)
        seen_ids.add(filled["id"])
        deduped.append(filled)

    lengths = [len(r["requirement"]) for r in deduped]
    lower_bound, upper_bound = compute_iqr_bounds(lengths)

    outlier_count = 0
    for r in deduped:
        char_len = len(r["requirement"])
        is_outlier = bool(char_len < lower_bound or char_len > upper_bound)
        r["requirement_char_length"] = char_len
        r["is_length_outlier"] = is_outlier
        if is_outlier:
            outlier_count += 1

    deduped.sort(key=lambda x: x["id"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)

    print(
        f"[clean] Cleaned {len(deduped)} scenarios "
        f"(IQR bounds: [{lower_bound:.1f}, {upper_bound:.1f}], outliers flagged: {outlier_count}) "
        f"-> {output_path}"
    )
    return deduped


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean merged SDLC benchmark dataset.")
    parser.add_argument("--input", type=Path, default=MERGED_RAW_PATH)
    parser.add_argument("--output", type=Path, default=PROCESSED_PATH)
    args = parser.parse_args()
    clean_dataset(args.input, args.output)


if __name__ == "__main__":
    main()


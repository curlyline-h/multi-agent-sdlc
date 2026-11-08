"""
Stratified 70/15/15 Dev/Val/Test Dataset Splitter.

Reads the cleaned 40-scenario benchmark (`data/processed/benchmark.json`) and
performs a two-stage stratified split by `category` using scikit-learn's
`train_test_split` with a fixed random seed (`RANDOM_SEED = 42`):
  - `dev.json`  : 70% (28 scenarios)
  - `val.json`  : 15% (6 scenarios)
  - `test.json` : 15% (6 scenarios)
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from sklearn.model_selection import train_test_split

ROOT_DIR = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT_DIR / "data" / "processed" / "benchmark.json"
SPLITS_DIR = ROOT_DIR / "data" / "splits"

RANDOM_SEED = 42


def create_stratified_splits(
    input_path: Path = BENCHMARK_PATH,
    splits_dir: Path = SPLITS_DIR,
    seed: int = RANDOM_SEED,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Split benchmark scenarios into 70% dev, 15% val, and 15% test sets,
    stratified by application category (`crud`, `rest_api`, `ecommerce`, `auth`, `db_app`).
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Processed benchmark not found at {input_path}")

    with open(input_path, "r", encoding="utf-8") as f:
        scenarios: List[Dict[str, Any]] = json.load(f)

    total = len(scenarios)
    if total < 10:
        raise ValueError(f"Expected at least 10 scenarios for stratified splitting, got {total}")

    categories = [s["category"] for s in scenarios]

    # Stage 1: 70% dev, 30% temp (val + test) stratified by category
    dev_set, temp_set = train_test_split(
        scenarios,
        test_size=0.30,
        random_state=seed,
        stratify=categories,
    )

    # Stage 2: Split the 30% temp set evenly into 15% val and 15% test.
    # Use category stratification when every class in temp_set has >= 2 members.
    temp_categories = [s["category"] for s in temp_set]
    temp_counts = Counter(temp_categories)
    stratify_stage2 = temp_categories if min(temp_counts.values()) >= 2 else None

    val_set, test_set = train_test_split(
        temp_set,
        test_size=0.50,
        random_state=seed,
        stratify=stratify_stage2,
    )

    dev_set.sort(key=lambda x: x["id"])
    val_set.sort(key=lambda x: x["id"])
    test_set.sort(key=lambda x: x["id"])

    splits_dir.mkdir(parents=True, exist_ok=True)
    splits = {
        "dev": dev_set,
        "val": val_set,
        "test": test_set,
    }

    for split_name, records in splits.items():
        out_file = splits_dir / f"{split_name}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        cat_dist = dict(sorted(Counter(r["category"] for r in records).items()))
        print(
            f"[split] Wrote {split_name}.json: {len(records)} scenarios "
            f"({len(records)/total:.0%}) | categories={cat_dist}"
        )

    return splits


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create stratified 70/15/15 dev/val/test splits for the SDLC benchmark."
    )
    parser.add_argument("--input", type=Path, default=BENCHMARK_PATH)
    parser.add_argument("--output-dir", type=Path, default=SPLITS_DIR)
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()
    create_stratified_splits(args.input, args.output_dir, args.seed)


if __name__ == "__main__":
    main()


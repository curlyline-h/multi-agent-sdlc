"""
Feature Engineering Strategy for SDLC Benchmark Scenarios.

Extracts structured tabular and text representations from `data/processed/benchmark.json`
using scikit-learn transformers:
  1. `OneHotEncoder` for categorical metadata (`category`, `source`)
  2. `MinMaxScaler` for numerical complexity indicators (character length, word count,
     functional requirement count, task count, max dependency DAG depth, security req count)
  3. `TfidfVectorizer` for n-gram lexical features over `requirement` and `expected_functional_reqs`
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder

ROOT_DIR = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT_DIR / "data" / "processed" / "benchmark.json"
FEATURES_META_PATH = ROOT_DIR / "data" / "processed" / "features_summary.json"


def compute_dag_depth(tasks: List[Dict[str, Any]]) -> int:
    """Compute the longest dependency chain depth (1-indexed) in a scenario's task DAG."""
    if not tasks:
        return 0
    deps_map = {
        t["title"]: list(t.get("depends_on", []))
        for t in tasks
        if isinstance(t, dict) and "title" in t
    }
    memo: Dict[str, int] = {}

    def _depth(title: str, visiting: set[str]) -> int:
        if title in memo:
            return memo[title]
        if title in visiting:
            return 1
        visiting.add(title)
        parents = [p for p in deps_map.get(title, []) if p in deps_map]
        d = 1 if not parents else 1 + max(_depth(p, visiting) for p in parents)
        visiting.remove(title)
        memo[title] = d
        return d

    return max(_depth(t, set()) for t in deps_map)


def build_feature_matrix(
    benchmark_path: Path = BENCHMARK_PATH,
    summary_output_path: Path = FEATURES_META_PATH,
) -> Dict[str, Any]:
    """Fit OneHotEncoder, MinMaxScaler, and TfidfVectorizer on the processed benchmark."""
    with open(benchmark_path, "r", encoding="utf-8") as f:
        scenarios: List[Dict[str, Any]] = json.load(f)

    categorical_rows = [[s["category"], s["source"]] for s in scenarios]
    ohe = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    categorical_encoded = ohe.fit_transform(categorical_rows)

    numeric_rows = []
    for s in scenarios:
        req_text = s["requirement"]
        char_len = len(req_text)
        word_count = len(req_text.split())
        func_count = len(s.get("expected_functional_reqs", []))
        task_count = len(s.get("tasks", []))
        dag_depth = compute_dag_depth(s.get("tasks", []))
        sec_count = len(s.get("security_reqs", []))
        numeric_rows.append(
            [char_len, word_count, func_count, task_count, dag_depth, sec_count]
        )

    scaler = MinMaxScaler()
    numeric_scaled = scaler.fit_transform(np.asarray(numeric_rows, dtype=float))

    corpus = [
        s["requirement"] + " " + " ".join(s.get("expected_functional_reqs", []))
        for s in scenarios
    ]
    tfidf = TfidfVectorizer(
        max_features=64,
        stop_words="english",
        ngram_range=(1, 2),
        sublinear_tf=True,
    )
    tfidf_matrix = tfidf.fit_transform(corpus).toarray()

    combined = np.hstack([categorical_encoded, numeric_scaled, tfidf_matrix])

    summary = {
        "num_scenarios": len(scenarios),
        "total_feature_dim": int(combined.shape[1]),
        "one_hot_feature_names": list(ohe.get_feature_names_out(["category", "source"])),
        "scaled_numeric_features": [
            "char_length",
            "word_count",
            "functional_req_count",
            "task_count",
            "max_dag_depth",
            "security_req_count",
        ],
        "numeric_min": [float(x) for x in scaler.data_min_],
        "numeric_max": [float(x) for x in scaler.data_max_],
        "top_tfidf_terms": list(tfidf.get_feature_names_out()[:25]),
    }

    summary_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(
        f"[features] Engineered feature matrix shape={combined.shape} "
        f"(OHE={categorical_encoded.shape[1]}, Scaled={numeric_scaled.shape[1]}, "
        f"TF-IDF={tfidf_matrix.shape[1]}) -> {summary_output_path}"
    )
    return {"matrix": combined, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract features for SDLC benchmark.")
    parser.add_argument("--input", type=Path, default=BENCHMARK_PATH)
    parser.add_argument("--output", type=Path, default=FEATURES_META_PATH)
    args = parser.parse_args()
    build_feature_matrix(args.input, args.output)


if __name__ == "__main__":
    main()


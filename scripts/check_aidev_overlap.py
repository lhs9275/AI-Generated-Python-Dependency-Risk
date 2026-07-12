#!/usr/bin/env python3
"""Compute overlap and rule-of-three denominators for AIDev PR samples."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"

INITIAL_EVAL = RESULTS_DIR / "aidev_evaluation_v4.json"
SCALEUP_EVAL = RESULTS_DIR / "aidev_evaluation_scaleup.json"
INITIAL_STRAT = RESULTS_DIR / "aidev_stratification.csv"
SCALEUP_STRAT = RESULTS_DIR / "aidev_stratification_scaleup.csv"
OUT_JSON = RESULTS_DIR / "aidev_sample_overlap.json"
OUT_CSV = RESULTS_DIR / "aidev_sample_overlap.csv"


def _load_eval(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text())
    rows = data.get("per_pr") or []
    if not isinstance(rows, list):
        raise ValueError(f"{path} does not contain per_pr list")
    return rows


def _pr_key(row: dict[str, Any]) -> str | None:
    for field in ("url", "html_url", "pr_url"):
        value = row.get(field)
        if value:
            return str(value).rstrip("/")
    repo = row.get("repo_full_name") or row.get("repository")
    number = row.get("pull_request_number") or row.get("pr_number")
    if repo and number:
        return f"{repo}#{number}"
    return None


def _primary_count(rows: list[dict[str, Any]]) -> int:
    n = 0
    for row in rows:
        primary = row.get("primary_risks")
        if primary:
            n += 1
            continue
        risks = row.get("risks") or []
        if any(risk.get("stage") in {"S1", "S3"} for risk in risks):
            n += 1
    return n


def _runtime_new_dep_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    urls = set()
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if (row.get("has_runtime_add") or "").strip().lower() == "true":
                url = (row.get("url") or "").rstrip("/")
                if url:
                    urls.add(url)
    return urls


def _rule_of_three(n: int | None) -> float | None:
    if not n:
        return None
    return 3.0 / n


def main() -> int:
    initial_rows = _load_eval(INITIAL_EVAL)
    scaleup_rows = _load_eval(SCALEUP_EVAL)

    initial_keys = {_pr_key(row) for row in initial_rows}
    scaleup_keys = {_pr_key(row) for row in scaleup_rows}
    unidentified_initial = sum(1 for key in initial_keys if key is None)
    unidentified_scaleup = sum(1 for key in scaleup_keys if key is None)
    initial_keys.discard(None)
    scaleup_keys.discard(None)

    overlap = initial_keys & scaleup_keys
    union = initial_keys | scaleup_keys

    initial_runtime = _runtime_new_dep_urls(INITIAL_STRAT)
    scaleup_runtime = _runtime_new_dep_urls(SCALEUP_STRAT)
    union_runtime = (initial_runtime | scaleup_runtime) & union

    initial_primary = _primary_count(initial_rows)
    scaleup_primary = _primary_count(scaleup_rows)
    primary_by_url = {}
    for row in initial_rows + scaleup_rows:
        key = _pr_key(row)
        if not key:
            continue
        primary_by_url[key] = primary_by_url.get(key, False) or (_primary_count([row]) > 0)
    union_primary = sum(1 for key in union if primary_by_url.get(key, False))

    summary = {
        "initial_audit_n": len(initial_keys),
        "scaleup_n": len(scaleup_keys),
        "overlap_n": len(overlap),
        "union_unique_n": len(union),
        "initial_primary_risk_n": initial_primary,
        "scaleup_primary_risk_n": scaleup_primary,
        "union_primary_risk_n": union_primary,
        "initial_runtime_new_dependency_n": len(initial_runtime & initial_keys),
        "scaleup_runtime_new_dependency_n": len(scaleup_runtime & scaleup_keys),
        "union_runtime_new_dependency_n": len(union_runtime),
        "rule_of_three_initial": _rule_of_three(len(initial_keys)),
        "rule_of_three_scaleup": _rule_of_three(len(scaleup_keys)),
        "rule_of_three_union": _rule_of_three(len(union)),
        "rule_of_three_runtime_new_dep": _rule_of_three(len(scaleup_runtime & scaleup_keys)),
        "rule_of_three_union_runtime_new_dep": _rule_of_three(len(union_runtime)),
        "unidentified_initial_n": unidentified_initial,
        "unidentified_scaleup_n": unidentified_scaleup,
        "key_priority": ["pr_url", "repo_full_name#pull_request_number", "repository/pr_number", "url/html_url fallback"],
        "overlap_urls": sorted(overlap),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    rows = [
        {
            "sample_set": "Initial audit",
            "n_unique": len(initial_keys),
            "primary_s1_s3_risk": initial_primary,
            "rule_of_three_95_upper_bound": _rule_of_three(len(initial_keys)),
            "note": "parser validation and manual audit",
        },
        {
            "sample_set": "Scale-up sample",
            "n_unique": len(scaleup_keys),
            "primary_s1_s3_risk": scaleup_primary,
            "rule_of_three_95_upper_bound": _rule_of_three(len(scaleup_keys)),
            "note": "main AIDev precision sample",
        },
        {
            "sample_set": "Runtime-new-dependency subset",
            "n_unique": len(scaleup_runtime & scaleup_keys),
            "primary_s1_s3_risk": 0,
            "rule_of_three_95_upper_bound": _rule_of_three(len(scaleup_runtime & scaleup_keys)),
            "note": "scale-up subset",
        },
        {
            "sample_set": "Union",
            "n_unique": len(union),
            "primary_s1_s3_risk": union_primary,
            "rule_of_three_95_upper_bound": _rule_of_three(len(union)),
            "note": f"PR URL union; overlap={len(overlap)}",
        },
        {
            "sample_set": "Union runtime-new-dependency subset",
            "n_unique": len(union_runtime),
            "primary_s1_s3_risk": 0,
            "rule_of_three_95_upper_bound": _rule_of_three(len(union_runtime)),
            "note": "union subset where has_runtime_add=True in available stratification",
        },
    ]
    with OUT_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({
        "initial_audit_n": len(initial_keys),
        "scaleup_n": len(scaleup_keys),
        "overlap_n": len(overlap),
        "union_unique_n": len(union),
        "rule_of_three_union": _rule_of_three(len(union)),
        "scaleup_runtime_new_dependency_n": len(scaleup_runtime & scaleup_keys),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

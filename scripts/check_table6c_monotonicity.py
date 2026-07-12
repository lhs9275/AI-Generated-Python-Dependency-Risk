#!/usr/bin/env python3
"""Recompute Table 6c minimal-baseline decisions and check FalseBlock monotonicity.

This script starts from archived per-run result.json files. It does not
regenerate model outputs. S1+S2+S3 is derived from the archived B3 stage report
by filtering to stages S1/S2/S3 and applying the same PASS/WARN/BLOCK
aggregation policy. This keeps the Table 6c comparison on the same policy
snapshot as the manuscript's B3 rows and Table 4.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.adjudicator.metric_calculator import compute as compute_metrics
from pipeline.config import is_canonical_run

RESULTS_DIR = ROOT / "results"
BENCH_ROOT = ROOT / "bench"
DETAIL_CSV = RESULTS_DIR / "table6c_falseblock_monotonicity_check.csv"
VIOLATIONS_CSV = RESULTS_DIR / "violations_falseblock_monotonicity.csv"
SUMMARY_JSON = RESULTS_DIR / "table6c_monotonicity_summary.json"

MODEL_DISPLAY = {
    "Qwen2.5-Coder-7B-Instruct": "Qwen-7B",
    "Qwen2.5-Coder-14B-Instruct-AWQ": "Qwen-14B",
    "Qwen2.5-Coder-32B-Instruct-AWQ": "Qwen-32B",
    "deepseek-coder-6.7b-instruct": "DeepSeek-6.7B",
    "CodeLlama-7b-Instruct-hf": "CodeLlama-7B",
}
MODEL_ORDER = ["Qwen-7B", "Qwen-14B", "Qwen-32B", "DeepSeek-6.7B", "CodeLlama-7B"]

DETAIL_FIELDS = [
    "run_id",
    "model",
    "task_id",
    "family",
    "generation_condition",
    "oracle_risky_all",
    "oracle_safe",
    "decision_S1",
    "decision_S2",
    "decision_S3",
    "decision_S4",
    "decision_S5",
    "decision_S6",
    "decision_S123",
    "decision_B3",
    "block_S123",
    "block_B3",
    "falseblock_S123",
    "falseblock_B3",
    "reason_S123",
    "reason_B3",
]


def _collect_runs() -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for path in RESULTS_DIR.glob("task_*/*/result.json"):
        if not is_canonical_run(path.parent.name):
            continue
        try:
            run = json.loads(path.read_text())
        except Exception as exc:
            print(f"skip unreadable result: {path}: {exc}", file=sys.stderr)
            continue
        if not isinstance(run, dict):
            continue
        slug = (run.get("model_id") or "").rsplit("/", 1)[-1]
        if slug not in MODEL_DISPLAY:
            continue
        key = (run.get("task_id", ""), run.get("generation_condition", ""), slug)
        by_key[key] = run
    return [by_key[k] for k in sorted(by_key)]


def _reason(guard_result: dict[str, Any]) -> str:
    issues = guard_result.get("risk_report") or []
    parts = []
    for issue in issues:
        stage = issue.get("stage", "?")
        severity = issue.get("severity", "?")
        reason = issue.get("reason", "")
        parts.append(f"{stage}:{severity}:{reason}")
    return " | ".join(parts)


def _aggregate_decision(issues: list[dict[str, Any]]) -> str:
    if any(issue.get("severity") == "critical" for issue in issues):
        return "BLOCK"
    if any(issue.get("severity") in {"high", "medium", "warn"} for issue in issues):
        return "WARN"
    return "PASS"


def _stored_b3_guard(run: dict[str, Any]) -> dict[str, Any]:
    guard_by_mode = run.get("guard_by_mode") or {}
    stored = guard_by_mode.get("B3") or run.get("guard_result") or {}
    if "decision" not in stored:
        raise ValueError(f"stored B3 guard decision missing for run {run.get('run_id')}")
    return {
        "decision": stored["decision"],
        "risk_report": stored.get("risk_report") or [],
        "repair_feedback": None,
        "mode": "B3",
    }


def _subset_guard(run: dict[str, Any], stages: set[str], mode: str) -> dict[str, Any]:
    b3 = _stored_b3_guard(run)
    issues = [issue for issue in b3.get("risk_report", []) if issue.get("stage") in stages]
    return {
        "decision": _aggregate_decision(issues),
        "risk_report": issues,
        "repair_feedback": None,
        "mode": mode,
    }


def _b0_guard() -> dict[str, Any]:
    return {"decision": "PASS", "risk_report": [], "repair_feedback": None, "mode": "B0"}


def _mode_metrics(run: dict[str, Any], guard_result: dict[str, Any]) -> dict[str, Any]:
    adjudication = run.get("adjudication") or {}
    return compute_metrics(adjudication["functional"], adjudication["safety"], guard_result)


def _pct(count: int, n: int) -> float | None:
    if n == 0:
        return None
    return count / n


def main() -> int:
    RESULTS_DIR.mkdir(exist_ok=True)

    runs = _collect_runs()
    detail_rows: list[dict[str, Any]] = []
    violation_rows: list[dict[str, Any]] = []
    counts: dict[str, dict[str, defaultdict[str, int]]] = {
        model: defaultdict(lambda: defaultdict(int)) for model in MODEL_ORDER
    }
    model_counts = defaultdict(int)
    task_keys = set()

    for run in runs:
        slug = (run.get("model_id") or "").rsplit("/", 1)[-1]
        model = MODEL_DISPLAY[slug]
        task_id = run["task_id"]
        family = task_id.split("_")[1]
        generation_condition = run["generation_condition"]

        decisions: dict[str, str] = {}
        for stage in ("S1", "S2", "S3", "S4", "S5", "S6"):
            guard_result = _subset_guard(run, {stage}, f"{stage}_only")
            decisions[stage] = guard_result["decision"]

        guard_b0 = _b0_guard()
        guard_s1 = _subset_guard(run, {"S1"}, "S1_only")
        guard_s13 = _subset_guard(run, {"S1", "S3"}, "S1_S3")
        guard_s123 = _subset_guard(run, {"S1", "S2", "S3"}, "S1_S2_S3")
        guard_b3 = _stored_b3_guard(run)

        metrics_b0 = _mode_metrics(run, guard_b0)
        metrics_s1 = _mode_metrics(run, guard_s1)
        metrics_s13 = _mode_metrics(run, guard_s13)
        metrics_s123 = _mode_metrics(run, guard_s123)
        metrics_b3 = _mode_metrics(run, guard_b3)

        safety = (run.get("adjudication") or {}).get("safety") or {}
        oracle_safe = safety.get("safety_pass_core") is True
        oracle_risky_all = not oracle_safe

        block_s123 = guard_s123["decision"] == "BLOCK"
        block_b3 = guard_b3["decision"] == "BLOCK"
        falseblock_s123 = metrics_s123["guard_metrics"]["false_block"]
        falseblock_b3 = metrics_b3["guard_metrics"]["false_block"]

        row = {
            "run_id": run.get("run_id", ""),
            "model": model,
            "task_id": task_id,
            "family": family,
            "generation_condition": generation_condition,
            "oracle_risky_all": int(oracle_risky_all),
            "oracle_safe": int(oracle_safe),
            "decision_S1": decisions["S1"],
            "decision_S2": decisions["S2"],
            "decision_S3": decisions["S3"],
            "decision_S4": decisions["S4"],
            "decision_S5": decisions["S5"],
            "decision_S6": decisions["S6"],
            "decision_S123": guard_s123["decision"],
            "decision_B3": guard_b3["decision"],
            "block_S123": int(block_s123),
            "block_B3": int(block_b3),
            "falseblock_S123": int(falseblock_s123),
            "falseblock_B3": int(falseblock_b3),
            "reason_S123": _reason(guard_s123),
            "reason_B3": _reason(guard_b3),
        }
        detail_rows.append(row)
        if block_s123 and oracle_safe and not block_b3:
            violation_rows.append(row)

        model_counts[model] += 1
        task_keys.add((model, task_id, generation_condition))
        for mode, metrics in (
            ("B0", metrics_b0),
            ("S1_only", metrics_s1),
            ("S1_S3", metrics_s13),
            ("S1_S2_S3", metrics_s123),
            ("B3", metrics_b3),
        ):
            c = counts[model][mode]
            c["n"] += 1
            if metrics["accepted"]["risky_accepted_patch"]:
                c["risky"] += 1
            if metrics["guard_metrics"]["false_block"]:
                c["false_block"] += 1
            if metrics["accepted"]["patch_accepted"] is False:
                c["blocked"] += 1

    with DETAIL_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DETAIL_FIELDS)
        writer.writeheader()
        writer.writerows(detail_rows)

    with VIOLATIONS_CSV.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DETAIL_FIELDS)
        writer.writeheader()
        writer.writerows(violation_rows)

    table6c_recomputed = {}
    for model in MODEL_ORDER:
        table6c_recomputed[model] = {}
        for mode in ("B0", "S1_only", "S1_S3", "S1_S2_S3", "B3"):
            c = counts[model][mode]
            n = c["n"]
            table6c_recomputed[model][mode] = {
                "n": n,
                "risky_acc": _pct(c["risky"], n),
                "risky_n": c["risky"],
                "false_block": _pct(c["false_block"], n),
                "false_block_n": c["false_block"],
                "block_rate": _pct(c["blocked"], n),
                "blocked_n": c["blocked"],
            }

    total_n = len(detail_rows)
    expected_per_model = 240
    same_run_set = all(model_counts[m] == expected_per_model for m in MODEL_ORDER)
    summary = {
        "same_run_set": same_run_set,
        "same_policy": True,
        "policy_source": "archived B3 stage reports filtered to S1/S2/S3 and re-aggregated",
        "models": MODEL_ORDER,
        "model_run_counts": dict(model_counts),
        "total_runs_checked": total_n,
        "unique_model_task_condition_keys": len(task_keys),
        "violations": len(violation_rows),
        "violation_file": str(VIOLATIONS_CSV.relative_to(ROOT)),
        "detail_file": str(DETAIL_CSV.relative_to(ROOT)),
        "table6c_recomputed": table6c_recomputed,
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    print(json.dumps({
        "same_run_set": same_run_set,
        "same_policy": True,
        "total_runs_checked": total_n,
        "violations": len(violation_rows),
        "summary": str(SUMMARY_JSON.relative_to(ROOT)),
    }, indent=2))
    return 0 if not violation_rows else 1


if __name__ == "__main__":
    raise SystemExit(main())

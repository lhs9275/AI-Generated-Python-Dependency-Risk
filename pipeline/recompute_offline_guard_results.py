"""Recompute paper-facing guard results from stored canonical runs.

This replay uses only stored dependency changes, stored functional/safety
adjudication, and task-local frozen evidence. It never regenerates LLM outputs.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

import yaml

from .adjudicator.metric_calculator import compute as compute_metrics
from .audit_evidence_coverage import find_task_dir
from .compute_additional_baselines import collect_runs
from .guard.decision import run_guard


DEFAULT_OUT = Path("results/offline_v2/canonical_runs.jsonl")
DEFAULT_DELTA_OUT = Path("results/offline_v2/decision_delta_summary.json")
RECOMPUTE_MODES = [
    "B0",
    "S1_only",
    "S1_S2",
    "S1_S3",
    "S1_S2_S3",
    "B2",
    "B3",
    "B3_no_S1",
    "B3_no_S2",
    "B3_no_S3",
    "B3_no_S4",
    "B3_no_S5",
    "B3_no_S6",
]
IDENTITY_FIELDS = (
    "task_id",
    "model_id",
    "generation_condition",
    "run_id",
    "_path",
    "seed",
    "temperature",
)
STORED_METRIC_MODES = ("B1_scanner",)


def read_jsonl(path: Path) -> list[dict]:
    """Read a JSONL file, ignoring blank lines."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(rows: Iterable[dict], path: Path) -> None:
    """Write rows as deterministic JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def _load_task_context(task_id: str, bench_root: Path) -> tuple[dict, dict]:
    task_dir = find_task_dir(bench_root, task_id)
    evidence_refs = json.loads((task_dir / "evidence_refs.json").read_text(encoding="utf-8"))
    policy = yaml.safe_load((task_dir / "dependency_policy.yaml").read_text(encoding="utf-8"))
    return evidence_refs, policy or {}


def _previous_decisions(run: dict) -> dict[str, str]:
    decisions = {}
    for mode, guard in (run.get("guard_by_mode") or {}).items():
        if isinstance(guard, dict) and guard.get("decision") is not None:
            decisions[mode] = guard["decision"]
    guard_result = run.get("guard_result") or {}
    if "B3" not in decisions and isinstance(guard_result, dict) and guard_result.get("decision"):
        decisions["B3"] = guard_result["decision"]
    return decisions


def _sort_key(run: dict) -> tuple[str, str, str, str, str]:
    return (
        str(run.get("task_id") or ""),
        str(run.get("generation_condition") or ""),
        str(run.get("model_id") or ""),
        str(run.get("run_id") or ""),
        str(run.get("_path") or ""),
    )


def recompute_one(
    run: dict,
    evidence_refs: dict,
    policy: dict,
    modes: Iterable[str] = RECOMPUTE_MODES,
) -> dict:
    """Recompute strict-offline guard and metrics for one stored run record."""
    adjudication = run.get("adjudication") or {}
    func_result = adjudication.get("functional") or {}
    safety_result = adjudication.get("safety") or {}
    dep_changes = run.get("dep_changes") or []

    guard_by_mode = {}
    metrics_by_mode = {}

    old_guard_by_mode = run.get("guard_by_mode") or {}
    old_metrics_by_mode = run.get("metrics_by_mode") or {}
    for mode in STORED_METRIC_MODES:
        if mode in old_guard_by_mode:
            guard_by_mode[mode] = old_guard_by_mode[mode]
        if mode in old_metrics_by_mode:
            metrics_by_mode[mode] = old_metrics_by_mode[mode]

    for mode in modes:
        guard = run_guard(
            dep_changes,
            evidence_refs,
            policy,
            mode=mode,
            missing_evidence="strict",
        )
        guard_by_mode[mode] = guard
        metrics_by_mode[mode] = compute_metrics(func_result, safety_result, guard)

    row = {field: run[field] for field in IDENTITY_FIELDS if field in run}
    row.update({
        "adjudication": adjudication,
        "dep_changes": dep_changes,
        "previous_decisions": _previous_decisions(run),
        "guard_by_mode": guard_by_mode,
        "metrics_by_mode": metrics_by_mode,
    })
    return row


def recompute_runs(runs: Iterable[dict], bench_root: Path) -> list[dict]:
    """Recompute all supplied runs in stable order."""
    rows = []
    for run in sorted(runs, key=_sort_key):
        evidence_refs, policy = _load_task_context(str(run["task_id"]), bench_root)
        rows.append(recompute_one(run, evidence_refs, policy))
    return rows


def decision_delta_summary(
    rows: Iterable[dict],
    modes: Iterable[str] = RECOMPUTE_MODES,
) -> dict:
    """Summarize old-vs-new guard decision changes for recomputed modes."""
    mode_summaries = {}
    row_list = list(rows)
    for mode in modes:
        pairs = Counter()
        compared = changed = missing_old = missing_new = not_comparable = 0
        for row in row_list:
            old = (row.get("previous_decisions") or {}).get(mode)
            guard = (row.get("guard_by_mode") or {}).get(mode) or {}
            new = guard.get("decision") if isinstance(guard, dict) else None
            if old is None:
                missing_old += 1
            if new is None:
                missing_new += 1
            if old is None or new is None:
                not_comparable += 1
                continue
            compared += 1
            if old != new:
                changed += 1
            pairs[f"{old}->{new}"] += 1
        mode_summaries[mode] = {
            "compared": compared,
            "changed": changed,
            "missing_old": missing_old,
            "missing_new": missing_new,
            "not_comparable": not_comparable,
            "old_new_pairs": dict(sorted(pairs.items())),
        }
    return {
        "n_runs": len(row_list),
        "modes": mode_summaries,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bench-root", type=Path, default=Path("bench"))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--delta-out", type=Path, default=DEFAULT_DELTA_OUT)
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_arg_parser().parse_args(argv)
    rows = recompute_runs(collect_runs(), args.bench_root)
    summary = decision_delta_summary(rows)

    write_jsonl(rows, args.out)
    args.delta_out.parent.mkdir(parents=True, exist_ok=True)
    args.delta_out.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"strict-offline runs: {len(rows)} -> {args.out}")
    print(f"decision delta summary -> {args.delta_out}")
    return summary


if __name__ == "__main__":
    main()

"""Export primary-risk real-PR cases from the naturalistic TSE gap-closure corpus."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


PRIMARY_LABELS = {
    "P1_NONEXISTENT_PACKAGE",
    "P2_INVALID_VERSION_SPEC",
    "P3_DIRECT_KNOWN_VULNERABILITY",
}
SAFE_LABEL = "NONE"

EXPORT_COLUMNS = [
    "change_id",
    "pr_id",
    "repo",
    "pr_url",
    "created_at",
    "tool_evidence",
    "manifest_file",
    "package_name",
    "new_spec",
    "change_type",
    "label_primary",
    "primary_grade",
    "label_confidence",
    "evidence_source",
    "adjudication_result",
]

GATE_VARIANTS = [
    "B0_no_gate",
    "S1S2S3_direct_evidence",
    "B3_full_guard",
]


def _tool_name(tool_evidence: str) -> str:
    return (tool_evidence or "unknown").split(":")[-1] or "unknown"


def export_primary_cases(labels_csv: Path, out_csv: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with Path(labels_csv).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("change_type") not in {"add", "version_change"}:
                continue
            if row.get("label_primary") not in PRIMARY_LABELS:
                continue

            change_id = row.get("change_id", "")
            if not change_id or change_id in seen:
                continue
            if not row.get("pr_id") or not row.get("package_name"):
                continue

            rows.append({column: row.get(column, "") for column in EXPORT_COLUMNS})
            seen.add(change_id)

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    with Path(out_csv).open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def load_analysis_cases(
    labels_csv: Path,
    decisions: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    analysis_labels = PRIMARY_LABELS | {SAFE_LABEL}
    with Path(labels_csv).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("change_type") not in {"add", "version_change"}:
                continue
            if row.get("label_primary") not in analysis_labels:
                continue

            change_id = row.get("change_id", "")
            if not change_id or change_id in seen:
                continue
            if change_id not in decisions:
                continue
            if not row.get("pr_id") or not row.get("package_name"):
                continue

            exported = {column: row.get(column, "") for column in EXPORT_COLUMNS}
            exported["risk_class"] = (
                "primary" if row.get("label_primary") in PRIMARY_LABELS else "safe"
            )
            rows.append(exported)
            seen.add(change_id)
    return rows


def load_guard_decisions(guard_jsonl: Path) -> dict[str, dict[str, str]]:
    decisions: dict[str, dict[str, str]] = {}
    with Path(guard_jsonl).open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            decisions[row["change_id"]] = row.get("decisions", {})
    return decisions


def _partition(
    cases: list[dict[str, str]],
    decisions: dict[str, dict[str, str]],
    variant: str,
) -> dict[str, int]:
    counts = Counter()
    for case in cases:
        decision = decisions.get(case["change_id"], {}).get(variant, "MISSING")
        counts[decision] += 1
    return {key: counts.get(key, 0) for key in ("BLOCK", "WARN", "PASS", "MISSING")}


def _ratio(numerator: int, denominator: int) -> float | None:
    if not denominator:
        return None
    return numerator / denominator


def summarize_decision_matrix(
    cases: list[dict[str, str]],
    decisions: dict[str, dict[str, str]],
    variant: str,
) -> dict:
    primary_cases = [case for case in cases if case.get("risk_class") == "primary"]
    safe_cases = [case for case in cases if case.get("risk_class") == "safe"]
    primary = _partition(primary_cases, decisions, variant)
    safe = _partition(safe_cases, decisions, variant)
    n_primary = len(primary_cases)
    n_safe = len(safe_cases)

    primary_block_or_warn = primary["BLOCK"] + primary["WARN"]
    safe_block_or_warn = safe["BLOCK"] + safe["WARN"]
    block_total = primary["BLOCK"] + safe["BLOCK"]
    flagged_total = primary_block_or_warn + safe_block_or_warn

    return {
        "variant": variant,
        "n_primary": n_primary,
        "n_safe": n_safe,
        "counts": {
            "primary": primary,
            "safe": safe,
        },
        "row_rates": {
            "primary": {
                decision: _ratio(count, n_primary)
                for decision, count in primary.items()
            },
            "safe": {
                decision: _ratio(count, n_safe)
                for decision, count in safe.items()
            },
        },
        "primary_block_recall": _ratio(primary["BLOCK"], n_primary),
        "primary_detection_recall_block_or_warn": _ratio(
            primary_block_or_warn,
            n_primary,
        ),
        "block_precision": _ratio(primary["BLOCK"], block_total),
        "flagged_precision_block_or_warn": _ratio(
            primary_block_or_warn,
            flagged_total,
        ),
        "safe_block_rate": _ratio(safe["BLOCK"], n_safe),
        "safe_burden_block_or_warn": _ratio(safe_block_or_warn, n_safe),
        "safe_pass_rate": _ratio(safe["PASS"], n_safe),
    }


def summarize_primary_cases(
    cases: list[dict[str, str]],
    decisions: dict[str, dict[str, str]],
    analysis_cases: list[dict[str, str]] | None = None,
) -> dict:
    n = len(cases)
    label_counts = Counter(case["label_primary"] for case in cases)
    tool_counts = Counter(_tool_name(case.get("tool_evidence", "")) for case in cases)
    gate_partitions = {
        variant: _partition(cases, decisions, variant) for variant in GATE_VARIANTS
    }
    b3 = gate_partitions["B3_full_guard"]
    detected = b3["BLOCK"] + b3["WARN"]
    summary = {
        "corpus_role": (
            "Guard-independent naturalistic primary-risk evidence; not a live "
            "deployment or end-to-end intervention claim."
        ),
        "n_primary_risk_changes": n,
        "n_unique_prs": len({case["pr_id"] for case in cases}),
        "n_unique_repos": len({case["repo"] for case in cases}),
        "by_primary_label": {
            label: label_counts.get(label, 0) for label in sorted(PRIMARY_LABELS)
        },
        "by_tool": dict(sorted(tool_counts.items())),
        "gate_partitions": gate_partitions,
        "b3_block_only_enforcement_recall": b3["BLOCK"] / n if n else None,
        "b3_detection_recall_block_or_warn": detected / n if n else None,
        "b3_silent_pass_floor": b3["PASS"] / n if n else None,
        "n_missing_guard_decisions": b3["MISSING"],
    }
    if analysis_cases is not None:
        summary["analysis_population"] = {
            "n_changes": len(analysis_cases),
            "n_primary": sum(
                1 for case in analysis_cases if case.get("risk_class") == "primary"
            ),
            "n_safe": sum(
                1 for case in analysis_cases if case.get("risk_class") == "safe"
            ),
            "population_rule": (
                "add/version changes with primary-risk or NONE labels and archived "
                "guard decisions"
            ),
        }
        summary["decision_matrix"] = {
            variant: summarize_decision_matrix(analysis_cases, decisions, variant)
            for variant in GATE_VARIANTS
        }
    return summary


def write_summary(summary: dict, out_json: Path) -> None:
    Path(out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(out_json).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path("results/tse_gap_closure/data/independent_labels.csv"),
    )
    parser.add_argument(
        "--guard",
        type=Path,
        default=Path("results/tse_gap_closure/data/guard_outputs.jsonl"),
    )
    parser.add_argument(
        "--out-csv",
        type=Path,
        default=Path("results/tse_gap_closure/analysis/risk_positive_primary_cases.csv"),
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=Path("results/tse_gap_closure/analysis/risk_positive_primary_summary.json"),
    )
    args = parser.parse_args()

    decisions = load_guard_decisions(args.guard)
    cases = export_primary_cases(args.labels, args.out_csv)
    analysis_cases = load_analysis_cases(args.labels, decisions)
    summary = summarize_primary_cases(cases, decisions, analysis_cases)
    write_summary(summary, args.out_json)
    print(f"primary-risk cases: {summary['n_primary_risk_changes']}")
    print(f"B3 block/warn/pass: {summary['gate_partitions']['B3_full_guard']}")
    print(
        "B3 safe block/warn/pass: "
        f"{summary['decision_matrix']['B3_full_guard']['counts']['safe']}"
    )


if __name__ == "__main__":
    main()

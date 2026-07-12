"""
Audit canonical result records for frozen S1 package-existence evidence coverage.

This module is deliberately snapshot-only. It does not query PyPI; it reports
which canonical dependency changes still require frozen evidence backfill.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Iterable

from .compute_additional_baselines import collect_runs
from .stdlib_names import is_stdlib


MISSING_CSV = "canonical_missing_s1_packages.csv"
SUMMARY_JSON = "summary.json"
LEGACY_MARKERS = ("pypi_live", "package_existence_unknown", "snapshot_missing")
_SNAPSHOT_ABSENT = object()
OUTPUT_FIELDS = [
    "task_id",
    "generation_condition",
    "model_id",
    "result_path",
    "task_dir",
    "evidence_refs_path",
    "change_type",
    "package_raw",
    "package_normalized",
    "stdlib",
    "present",
    "evidence_status",
    "exists_value",
    "snapshot_key",
]


def normalize_package(name: str) -> str:
    """Normalize package names with the same PEP 503-style rule used by S1."""
    return re.sub(r"[-_.]+", "-", name).lower()


def find_task_dir(bench_root: Path, task_id: str) -> Path:
    """Find a benchmark task directory under bench/F*_*/<task_id>."""
    matches = sorted(bench_root.glob(f"F*_*/{task_id}"))
    if not matches:
        raise FileNotFoundError(f"task directory not found under {bench_root}: {task_id}")
    return matches[0]


def _load_evidence_refs(task_dir: Path) -> tuple[dict, Path]:
    evidence_path = task_dir / "evidence_refs.json"
    if not evidence_path.exists():
        return {}, evidence_path
    return json.loads(evidence_path.read_text(encoding="utf-8")), evidence_path


def _snapshot_lookup(snapshot: dict, package_name: str) -> tuple[str | None, object]:
    package_norm = normalize_package(package_name)
    for key, entry in snapshot.items():
        if normalize_package(str(key)) == package_norm:
            return str(key), entry
    return None, _SNAPSHOT_ABSENT


def _run_key(run: dict) -> str:
    result_path = str(run.get("_path") or "")
    if result_path:
        return result_path
    return "|".join([
        str(run.get("task_id", "")),
        str(run.get("generation_condition", "")),
        str(run.get("model_id", "")),
    ])


def _row_base(run: dict, task_dir: Path, evidence_path: Path, change: dict) -> dict:
    package_raw = str(change.get("package") or "")
    return {
        "task_id": str(run.get("task_id") or ""),
        "generation_condition": str(run.get("generation_condition") or ""),
        "model_id": str(run.get("model_id") or ""),
        "result_path": str(run.get("_path") or ""),
        "run_key": _run_key(run),
        "task_dir": str(task_dir),
        "evidence_refs_path": str(evidence_path),
        "change_type": str(change.get("change_type") or ""),
        "package_raw": package_raw,
        "package_normalized": normalize_package(package_raw),
    }


def audit_run_record(run: dict, task_dir: Path) -> list[dict]:
    """Audit added/modified dependency changes in one canonical run record."""
    evidence_refs, evidence_path = _load_evidence_refs(task_dir)
    snapshot = evidence_refs.get("pypi_packages") or {}
    rows = []

    for change in run.get("dep_changes") or []:
        if change.get("change_type") not in {"added", "modified"}:
            continue
        package_raw = str(change.get("package") or "")
        if not package_raw:
            continue

        base = _row_base(run, task_dir, evidence_path, change)
        if is_stdlib(package_raw):
            rows.append({
                **base,
                "stdlib": True,
                "present": True,
                "evidence_status": "stdlib",
                "exists_value": None,
                "snapshot_key": "",
            })
            continue

        snapshot_key, entry = _snapshot_lookup(snapshot, package_raw)
        if entry is _SNAPSHOT_ABSENT:
            rows.append({
                **base,
                "stdlib": False,
                "present": False,
                "evidence_status": "absent",
                "exists_value": None,
                "snapshot_key": "",
            })
            continue

        if not isinstance(entry, dict):
            exists = entry
            present = False
            status = "malformed"
        else:
            exists = entry.get("exists")
            if exists is True or exists is False:
                present = True
                status = "covered"
            elif exists is None:
                present = False
                status = "incomplete"
            else:
                present = False
                status = "malformed"

        rows.append({
            **base,
            "stdlib": False,
            "present": present,
            "evidence_status": status,
            "exists_value": exists,
            "snapshot_key": snapshot_key or "",
        })

    return rows


def _is_missing_row(row: dict) -> bool:
    return not row.get("present") and not row.get("stdlib")


def _legacy_marker_counts(runs: Iterable[dict]) -> dict[str, int]:
    counts = {marker: 0 for marker in LEGACY_MARKERS}
    for run in runs:
        text = json.dumps(run, sort_keys=True, ensure_ascii=False)
        for marker in LEGACY_MARKERS:
            counts[marker] += text.count(marker)
    return counts


def audit_runs(runs: list[dict], bench_root: Path) -> tuple[list[dict], dict[str, int], int]:
    rows = []
    task_ids = set()
    for run in runs:
        task_id = str(run.get("task_id") or "")
        if not task_id:
            continue
        task_ids.add(task_id)
        rows.extend(audit_run_record(run, find_task_dir(bench_root, task_id)))
    return rows, _legacy_marker_counts(runs), len(task_ids)


def _csv_value(value: object) -> object:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    return value


def _write_csv(rows: list[dict], out_path: Path) -> None:
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in OUTPUT_FIELDS})


def write_outputs(
    rows: list[dict],
    out_dir: Path,
    *,
    runs_audited: int | None = None,
    task_count: int | None = None,
    legacy_marker_counts: dict[str, int] | None = None,
) -> dict:
    """Write missing evidence CSV and summary JSON, returning the summary."""
    out_dir.mkdir(parents=True, exist_ok=True)
    missing_rows = sorted(
        (row for row in rows if _is_missing_row(row)),
        key=lambda row: (
            str(row.get("task_id") or ""),
            str(row.get("generation_condition") or ""),
            str(row.get("model_id") or ""),
            str(row.get("package_normalized") or ""),
            str(row.get("package_raw") or ""),
            str(row.get("result_path") or ""),
            str(row.get("evidence_status") or ""),
        ),
    )

    marker_counts = {marker: 0 for marker in LEGACY_MARKERS}
    if legacy_marker_counts:
        marker_counts.update(legacy_marker_counts)

    if runs_audited is None:
        runs_audited = len({row.get("run_key") for row in rows if row.get("run_key")})
    if task_count is None:
        task_count = len({row.get("task_id") for row in rows if row.get("task_id")})

    summary = {
        "runs_audited": runs_audited,
        "dep_changes_audited": len(rows),
        "missing_rows": len(missing_rows),
        "unique_missing_packages": len({
            row.get("package_normalized") for row in missing_rows if row.get("package_normalized")
        }),
        "task_count": task_count,
        "legacy_marker_counts": marker_counts,
    }

    _write_csv(missing_rows, out_dir / MISSING_CSV)
    (out_dir / SUMMARY_JSON).write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit canonical runs for missing frozen S1 PyPI evidence.",
    )
    parser.add_argument("--bench-root", type=Path, default=Path("bench"))
    parser.add_argument("--out-dir", type=Path, default=Path("results/evidence_coverage"))
    parser.add_argument("--canonical-only", action="store_true", default=True)
    parser.add_argument("--fail-on-missing", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> dict:
    args = build_arg_parser().parse_args(argv)
    runs = collect_runs()
    rows, marker_counts, task_count = audit_runs(runs, args.bench_root)
    summary = write_outputs(
        rows,
        args.out_dir,
        runs_audited=len(runs),
        task_count=task_count,
        legacy_marker_counts=marker_counts,
    )
    if args.fail_on_missing and summary["missing_rows"]:
        raise SystemExit(
            f"{summary['missing_rows']} canonical S1 packages missing frozen evidence"
        )
    return summary


if __name__ == "__main__":
    main()

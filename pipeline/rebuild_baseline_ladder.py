"""P2: rebuild the baseline ladder over frozen evidence.

Repositions pip-audit as an off-the-shelf negative-control baseline and makes the
direct public-evidence core (S1/S2/S3) the spine of the ladder. For each canonical
run we reuse the stored generated patch (dep_changes) and the task's *frozen*
evidence/policy, then re-run run_guard for every ladder rung and re-score with the
same adjudicator outputs. With --runs-jsonl, consume precomputed strict-offline
metrics instead of calling run_guard again. No generation, no live network
(frozen snapshots only).

Ladder: B0 -> B1_scanner(pip-audit, from stored) -> S1-only -> S1+S2 -> S1+S3
        -> S1+S2+S3 (direct public-evidence core) -> B2 (=S1+S3+S5) -> B3 (full).
"""

import argparse
import csv
import json
from pathlib import Path

import yaml

from pipeline.guard.decision import run_guard
from pipeline.adjudicator.metric_calculator import compute as compute_metrics
from pipeline.recompute_offline_guard_results import read_jsonl

GUARD_LADDER = ["B0", "S1_only", "S1_S2", "S1_S3", "S1_S2_S3", "B2", "B3"]
LADDER_DISPLAY = ["B0", "B1_scanner", "S1_only", "S1_S2", "S1_S3", "S1_S2_S3", "B2", "B3"]
REQUIRED_LADDER_MODES = tuple(GUARD_LADDER)
REQUIRED_ACCEPTED_FIELDS = (
    "patch_accepted",
    "functional_success",
    "safety_pass_core",
    "risky_accepted_patch",
)
REQUIRED_GUARD_METRIC_FIELDS = ("false_block",)


def _bench_task_dir(task_id: str, bench_root: Path) -> Path | None:
    hits = list(bench_root.glob(f"F*_*/{task_id}"))
    return hits[0] if hits else None


def _load_frozen(task_dir: Path):
    ev = json.loads((task_dir / "evidence_refs.json").read_text())
    policy = yaml.safe_load((task_dir / "dependency_policy.yaml").read_text())
    return ev, policy


def ladder_for_run(run: dict, bench_root: Path) -> dict | None:
    """RiskyAcc/AFSP per ladder rung for one run, re-running guard on frozen evidence."""
    task_dir = _bench_task_dir(run["task_id"], bench_root)
    if task_dir is None:
        return None
    ev, policy = _load_frozen(task_dir)
    dep = run.get("dep_changes") or []
    adj = run.get("adjudication", {})
    func_result = {"functional_success": adj.get("functional", {}).get("functional_success")}
    safety_result = {"safety_pass_core": adj.get("safety", {}).get("safety_pass_core")}

    out = {}
    for mode in GUARD_LADDER:
        guard = run_guard(dep, ev, policy, mode=mode)
        m = compute_metrics(func_result, safety_result, guard)
        out[mode] = {
            "risky_accepted": bool(m["accepted"]["risky_accepted_patch"]),
            "accepted": bool(m["accepted"]["patch_accepted"]),
            "afsp": bool(m["accepted"]["patch_accepted"]
                         and m["accepted"]["functional_success"]
                         and m["accepted"]["safety_pass_core"]),
            "false_block": bool(m["guard_metrics"]["false_block"]),
        }
    # pip-audit baseline comes from the stored per-run scoring (already computed offline)
    scan = run.get("metrics_by_mode", {}).get("B1_scanner")
    if scan:
        out["B1_scanner"] = {
            "risky_accepted": bool(scan["accepted"].get("risky_accepted_patch")),
            "accepted": bool(scan["accepted"].get("patch_accepted")),
            "afsp": bool(scan["accepted"].get("patch_accepted")
                         and scan["accepted"].get("functional_success")
                         and scan["accepted"].get("safety_pass_core")),
            "false_block": bool(scan["guard_metrics"].get("false_block")),
        }
    return out


def _cell_from_metrics(metrics: dict) -> dict:
    accepted = metrics.get("accepted") or {}
    guard_metrics = metrics.get("guard_metrics") or {}
    patch_accepted = bool(accepted.get("patch_accepted"))
    return {
        "risky_accepted": bool(accepted.get("risky_accepted_patch")),
        "accepted": patch_accepted,
        "afsp": bool(
            patch_accepted
            and accepted.get("functional_success")
            and accepted.get("safety_pass_core")
        ),
        "false_block": bool(guard_metrics.get("false_block")),
    }


def _row_label(row: dict, index: int) -> str:
    task = row.get("task_id")
    model = row.get("model_id")
    cond = row.get("generation_condition")
    bits = [str(x) for x in (task, model, cond) if x]
    return f"row {index}" + (f" ({' / '.join(bits)})" if bits else "")


def _validate_required_metrics(row: dict, required_modes: tuple[str, ...], index: int) -> None:
    metrics_by_mode = row.get("metrics_by_mode") or {}
    invalid = []
    for mode in required_modes:
        if not _valid_metric_cell(metrics_by_mode.get(mode)):
            invalid.append(mode)
    if invalid:
        raise ValueError(
            f"{_row_label(row, index)} missing required metrics_by_mode cells: "
            f"{', '.join(invalid)}"
        )


def _valid_metric_cell(metrics: object) -> bool:
    if not isinstance(metrics, dict):
        return False
    accepted = metrics.get("accepted")
    guard_metrics = metrics.get("guard_metrics")
    if not isinstance(accepted, dict) or not isinstance(guard_metrics, dict):
        return False
    if any(field not in accepted for field in REQUIRED_ACCEPTED_FIELDS):
        return False
    if any(field not in guard_metrics for field in REQUIRED_GUARD_METRIC_FIELDS):
        return False
    bool_fields = (
        accepted.get("patch_accepted"),
        accepted.get("risky_accepted_patch"),
        guard_metrics.get("false_block"),
    )
    if any(not isinstance(value, bool) for value in bool_fields):
        return False
    nullable_bool_fields = (
        accepted.get("functional_success"),
        accepted.get("safety_pass_core"),
    )
    return all(value is None or isinstance(value, bool) for value in nullable_bool_fields)


def ladder_for_precomputed_run(row: dict) -> dict:
    """RiskyAcc/AFSP cells from strict-offline precomputed metrics."""
    metrics_by_mode = row.get("metrics_by_mode") or {}
    out = {}
    for mode in LADDER_DISPLAY:
        if mode not in metrics_by_mode:
            continue
        metrics = metrics_by_mode.get(mode)
        if not _valid_metric_cell(metrics):
            raise ValueError(f"invalid metrics_by_mode cell for mode: {mode}")
        out[mode] = _cell_from_metrics(metrics)
    return out


def ladders_from_runs_jsonl(
    path: Path,
    required_modes: tuple[str, ...] = REQUIRED_LADDER_MODES,
) -> list[tuple[dict, dict]]:
    """Return (run row, ladder cells) pairs from a strict-offline JSONL file."""
    pairs = []
    for index, row in enumerate(read_jsonl(path), start=1):
        _validate_required_metrics(row, required_modes, index)
        rung = ladder_for_precomputed_run(row)
        if rung:
            pairs.append((row, rung))
    return pairs


def aggregate(per_run: list[dict], modes: list[str]) -> dict:
    out = {}
    for mode in modes:
        cells = [r[mode] for r in per_run if mode in r]
        n = len(cells)
        if not n:
            continue
        out[mode] = {
            "n": n,
            "risky_accepted_rate_all": sum(c["risky_accepted"] for c in cells) / n,
            "afsp_all": sum(c["afsp"] for c in cells) / n,
            "false_block_rate_all": sum(c["false_block"] for c in cells) / n,
            "block_rate": sum(0 if c["accepted"] else 1 for c in cells) / n,
        }
    return out


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bench-root", type=Path, default=Path("bench"))
    ap.add_argument("--out-dir", type=Path, default=Path("results/metrics_v2"))
    ap.add_argument("--runs-jsonl", type=Path)
    args = ap.parse_args(argv)

    per_run, per_run_by_model = [], {}
    if args.runs_jsonl:
        run_pairs = ladders_from_runs_jsonl(args.runs_jsonl)
        for r, rung in run_pairs:
            per_run.append(rung)
            slug = r.get("model_id", "").rsplit("/", 1)[-1]
            per_run_by_model.setdefault(slug, []).append(rung)
    else:
        from pipeline.compute_additional_baselines import collect_runs
        runs = collect_runs()

        for r in runs:
            rung = ladder_for_run(r, args.bench_root)
            if rung is None:
                continue
            per_run.append(rung)
            slug = r.get("model_id", "").rsplit("/", 1)[-1]
            per_run_by_model.setdefault(slug, []).append(rung)

    data = {"pooled": aggregate(per_run, LADDER_DISPLAY)}
    for slug, rows in per_run_by_model.items():
        data[slug] = aggregate(rows, LADDER_DISPLAY)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with (args.out_dir / "table5_baseline_ladder_v2.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["model", "mode", "n", "risky_accepted_rate_all", "afsp_all",
                    "false_block_rate_all", "block_rate"])
        for model in data:
            for mode in LADDER_DISPLAY:
                m = data[model].get(mode)
                if m:
                    w.writerow([model, mode, m["n"], round(m["risky_accepted_rate_all"], 4),
                                round(m["afsp_all"], 4), round(m["false_block_rate_all"], 4),
                                round(m["block_rate"], 4)])
    (args.out_dir / "baseline_ladder_v2_full.json").write_text(json.dumps(data, indent=2))

    print(f"runs with frozen evidence: {len(per_run)} -> {args.out_dir}/table5_baseline_ladder_v2.csv")
    print(f"{'mode':12s} {'RiskyAcc-All':>13s} {'AFSP-All':>9s} {'FalseBlock':>11s}")
    for mode in LADDER_DISPLAY:
        m = data["pooled"].get(mode)
        if m:
            print(f"{mode:12s} {m['risky_accepted_rate_all']:>13.3f} {m['afsp_all']:>9.3f} "
                  f"{m['false_block_rate_all']:>11.3f}")


if __name__ == "__main__":
    main()

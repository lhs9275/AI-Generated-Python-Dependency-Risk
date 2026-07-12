#!/usr/bin/env python3
"""Per-model paired McNemar (B0 vs B3) for the primary RiskyAcc-Core (F1+F2+F3)
metric and, for completeness, RiskyAcc-All (F1--F6), with a Holm--Bonferroni
adjustment over the five primary (per-model) Core comparisons.

This backs the manuscript's primary-comparison significance sentence
("the five primary B0-vs-B3 comparisons are significant under Bonferroni/Holm,
McNemar exact"; Sections IV-A and IV-B). It recomputes the per-model exact
McNemar p-values directly from the archived per-run result.json files (the same
source compute_tse_stats reads) so the claim is reproducible offline with no GPU.

Output: results/primary_mcnemar_holm.json
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from .compute_tse_stats import collect_runs, mode_val, MODEL_DISPLAY
from .stats_paired import _mcnemar_exact

CORE_FAMILIES = {"F1", "F2", "F3"}


def _family(task_id: str) -> str:
    return task_id.split("_")[1]


def _paired_counts(runs, core_only: bool):
    """Paired 2x2 over matched runs: b=B0-risky&B3-safe, c=B0-safe&B3-risky."""
    b = c = both1 = both0 = 0
    for r in runs:
        if core_only and _family(r["task_id"]) not in CORE_FAMILIES:
            continue
        xv = mode_val(r, "B0", "accepted", "risky_accepted_patch")
        yv = mode_val(r, "B3", "accepted", "risky_accepted_patch")
        if xv is None or yv is None:
            continue  # drop incomplete pair (like compute_table3); do not coerce None->safe
        x, y = bool(xv), bool(yv)
        if x and not y:
            b += 1
        elif (not x) and y:
            c += 1
        elif x and y:
            both1 += 1
        else:
            both0 += 1
    return b, c, both1, both0


def _per_model(results_dir: Path, core_only: bool, runs_jsonl: Path | None = None) -> dict:
    out = {}
    for slug, display in MODEL_DISPLAY.items():
        runs = collect_runs(results_dir, slug, runs_jsonl=runs_jsonl)
        b, c, both1, both0 = _paired_counts(runs, core_only)
        out[display] = {
            "b": int(b), "c": int(c), "both_risky": int(both1), "both_safe": int(both0),
            "n_pairs": int(b + c + both1 + both0),
            "p_value": float(_mcnemar_exact(b, c)),
        }
    return out


def _holm(pairs):
    """Holm--Bonferroni over [(label, p), ...]; returns label -> adjusted p (monotone)."""
    ordered = sorted(pairs, key=lambda x: x[1])
    m = len(ordered)
    adj = {}
    running = 0.0
    for i, (label, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - i) * float(p)))  # enforce monotonicity
        adj[label] = float(running)
    return adj


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", type=Path,
                    default=Path(__file__).resolve().parent.parent / "results")
    ap.add_argument("--runs-jsonl", type=Path, default=None)
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument(
        "--expect-core-pairs",
        type=int,
        default=None,
        help="Fail if any model has a different number of RiskyAcc-Core pairs.",
    )
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    core = _per_model(args.results_dir, core_only=True, runs_jsonl=args.runs_jsonl)
    allf = _per_model(args.results_dir, core_only=False, runs_jsonl=args.runs_jsonl)

    primary_pairs = [(m, core[m]["p_value"]) for m in core]
    holm_adj = _holm(primary_pairs)
    for m in core:
        core[m]["holm_adjusted_p"] = float(holm_adj[m])
        core[m]["significant_holm"] = bool(holm_adj[m] < args.alpha)

    n_sig = sum(1 for m in core if core[m]["significant_holm"])
    pair_count_failures = {}
    if args.expect_core_pairs is not None:
        pair_count_failures = {
            m: core[m]["n_pairs"]
            for m in MODEL_DISPLAY.values()
            if core[m]["n_pairs"] != args.expect_core_pairs
        }
    result = {
        "metric": "RiskyAcc paired McNemar (B0 vs B3), exact two-sided",
        "primary": "RiskyAcc-Core (F1+F2+F3, n_pairs=120/model)",
        "alpha": args.alpha,
        "multiple_comparison": "Holm-Bonferroni over the 5 primary per-model Core comparisons",
        "expected_core_pairs_per_model": args.expect_core_pairs,
        "core_pair_count_failures": pair_count_failures,
        "all_core_pair_counts_match_expected": not pair_count_failures,
        "core": core,
        "all": allf,
        "n_primary_significant_holm": n_sig,
        "all_primary_significant_holm": n_sig == len(core),
    }

    out = args.out or (args.results_dir / "primary_mcnemar_holm.json")
    out.write_text(json.dumps(result, indent=2))

    print(f"Primary RiskyAcc-Core paired McNemar (B0 vs B3), Holm alpha={args.alpha}:")
    for m in MODEL_DISPLAY.values():
        d = core[m]
        print(f"  {m:14s} b={d['b']:3d} c={d['c']:1d}  p={d['p_value']:.3e}  "
              f"p_holm={d['holm_adjusted_p']:.3e}  sig={d['significant_holm']}")
    print(f"All five primary comparisons significant under Holm: "
          f"{result['all_primary_significant_holm']} ({n_sig}/{len(core)})")
    print(f"Wrote {out}")

    failures = []
    if pair_count_failures:
        failures.append(
            "core pair-count check failed: "
            + ", ".join(
                f"{model}={actual} (expected {args.expect_core_pairs})"
                for model, actual in pair_count_failures.items()
            )
        )
    if n_sig != len(core):
        failures.append(
            f"only {n_sig}/{len(core)} primary Core comparisons significant "
            f"under Holm at alpha={args.alpha}"
        )
    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

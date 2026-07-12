"""P2: paired McNemar tests on the recomputed (frozen-evidence) ladder metrics.

Closes the txt command-2 deliverable `mcnemar_results_v2.json`. All contrasts are on
RiskyAcceptedRate_all (accepted AND oracle_risky), paired per canonical run:

  - B0 vs B3            does the full guard reduce risky acceptance vs no gate?
  - S1_S2_S3 vs B3      does anything beyond the direct public-evidence core matter?
No generation, no live network. By default this reuses
rebuild_baseline_ladder.ladder_for_run; with --runs-jsonl, it consumes
precomputed strict-offline ladder cells instead of calling run_guard again.
Uses the McNemar exact test + conditional odds ratio from pipeline.stats_paired.
"""

import argparse
import json
from pathlib import Path

from pipeline.stats_paired import _mcnemar_exact, _odds_ratio_ci
from pipeline.rebuild_baseline_ladder import ladder_for_run, ladders_from_runs_jsonl

CONTRASTS = [("B0", "B3"), ("S1_S2_S3", "B3")]
FIELD = "risky_accepted"
REQUIRED_JSONL_MODES = ("B0", "B3", "S1_S2_S3")


def paired_mcnemar(rows: list[dict], left: str, right: str, field: str = FIELD) -> dict:
    """McNemar exact test on a binary field across two ladder modes, paired per row.

    b = (left positive, right negative); c = (left negative, right positive).
    Rows missing either mode are skipped.
    """
    b = c = both1 = both0 = 0
    for r in rows:
        if left not in r or right not in r:
            continue
        lv = bool(r[left][field])
        rv = bool(r[right][field])
        if lv and not rv:
            b += 1
        elif not lv and rv:
            c += 1
        elif lv and rv:
            both1 += 1
        else:
            both0 += 1
    n = b + c + both1 + both0
    p = _mcnemar_exact(b, c)
    odds = _odds_ratio_ci(both1, b, c, both0)
    return {
        "left": left,
        "right": right,
        "field": field,
        "n_pairs": n,
        "left_pos": both1 + b,
        "right_pos": both1 + c,
        "discordant_b_left1_right0": b,
        "discordant_c_left0_right1": c,
        "both_pos": both1,
        "both_neg": both0,
        "p_value": round(p, 6),
        **odds,
    }


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bench-root", type=Path, default=Path("bench"))
    ap.add_argument("--out-dir", type=Path, default=Path("results/metrics_v2"))
    ap.add_argument("--runs-jsonl", type=Path)
    args = ap.parse_args(argv)

    if args.runs_jsonl:
        rows = [
            rung
            for _, rung in ladders_from_runs_jsonl(
                args.runs_jsonl,
                required_modes=REQUIRED_JSONL_MODES,
            )
        ]
    else:
        from pipeline.compute_additional_baselines import collect_runs
        runs = collect_runs()

        rows = []
        for r in runs:
            rung = ladder_for_run(r, args.bench_root)
            if rung is not None:
                rows.append(rung)

    results = {
        "field": FIELD,
        "n_runs_with_frozen_evidence": len(rows),
        "note": ("Paired McNemar exact test on RiskyAcceptedRate_all over frozen-evidence "
                 "re-run of run_guard. b=left-positive/right-negative, c=left-negative/"
                 "right-positive. odds_ratio is the conditional (discordant-pair) OR."),
        "contrasts": [paired_mcnemar(rows, lo, hi) for lo, hi in CONTRASTS],
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "mcnemar_results_v2.json").write_text(json.dumps(results, indent=2))

    print(f"runs paired: {len(rows)} -> {args.out_dir}/mcnemar_results_v2.json")
    print(f"{'contrast':22s} {'b':>4s} {'c':>4s} {'OR':>8s} {'p':>10s}")
    for ct in results["contrasts"]:
        print(f"{ct['left']+' vs '+ct['right']:22s} "
              f"{ct['discordant_b_left1_right0']:>4d} {ct['discordant_c_left0_right1']:>4d} "
              f"{str(ct['odds_ratio']):>8s} {ct['p_value']:>10.4g}")


if __name__ == "__main__":
    main()

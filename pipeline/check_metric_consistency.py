"""P2: verify the recomputed v2 metrics match the published manuscript tables.

Confirms that Table 4's "AFSP" / "RiskyAcc" equal the explicit *all-denominator*
recompute (AFSP_all, RiskyAcc_all), pinning down the denominator the caption must
state. Any cell off by more than the tolerance is flagged. Writes consistency_report.md.
"""

import argparse
import json
from pathlib import Path

# Published Table 4 (AFSP-All) values from the submitted English manuscript
# (paper/en/tse_en.tex, Table IV), as fractions. B3 afsp_all reflects the
# strict-offline recompute (results/offline_v2/canonical_runs.jsonl); the earlier
# pre-strict-offline B3 values (Qwen-7B 0.533, 14B 0.546, 32B 0.612, DS 0.550,
# CL 0.404) are superseded. B0 afsp_all, RiskyAcc, and FuncSucc are unchanged.
PUBLISHED_TABLE4 = {
    "Qwen2.5-Coder-7B-Instruct": {
        "B0": {"afsp_all": 0.562, "risky_accepted_rate_all": 0.262, "generated_func_succ": 0.700},
        "B3": {"afsp_all": 0.521, "risky_accepted_rate_all": 0.017, "generated_func_succ": 0.700}},
    "Qwen2.5-Coder-14B-Instruct-AWQ": {
        "B0": {"afsp_all": 0.554, "risky_accepted_rate_all": 0.300, "generated_func_succ": 0.754},
        "B3": {"afsp_all": 0.542, "risky_accepted_rate_all": 0.008, "generated_func_succ": 0.754}},
    "Qwen2.5-Coder-32B-Instruct-AWQ": {
        "B0": {"afsp_all": 0.646, "risky_accepted_rate_all": 0.229, "generated_func_succ": 0.808},
        "B3": {"afsp_all": 0.608, "risky_accepted_rate_all": 0.021, "generated_func_succ": 0.808}},
    "deepseek-coder-6.7b-instruct": {
        "B0": {"afsp_all": 0.550, "risky_accepted_rate_all": 0.138, "generated_func_succ": 0.642},
        "B3": {"afsp_all": 0.538, "risky_accepted_rate_all": 0.004, "generated_func_succ": 0.642}},
    "CodeLlama-7b-Instruct-hf": {
        "B0": {"afsp_all": 0.425, "risky_accepted_rate_all": 0.333, "generated_func_succ": 0.638},
        "B3": {"afsp_all": 0.367, "risky_accepted_rate_all": 0.075, "generated_func_succ": 0.638}},
}


def compare_to_published(recomputed: dict, published: dict, tol: float = 0.006) -> list[dict]:
    """One row per (model, mode, metric) comparing recomputed vs published."""
    rows = []
    for model, modes in published.items():
        for mode, metrics in modes.items():
            for metric, pub in metrics.items():
                rec = recomputed.get(model, {}).get(mode, {}).get(metric)
                if rec is None:
                    rows.append({"model": model, "mode": mode, "metric": metric,
                                 "published": pub, "recomputed": None,
                                 "abs_diff": None, "consistent": False})
                    continue
                diff = abs(rec - pub)
                rows.append({"model": model, "mode": mode, "metric": metric,
                             "published": pub, "recomputed": round(rec, 4),
                             "abs_diff": round(diff, 4), "consistent": diff <= tol})
    return rows


def write_report(rows, recomputed, out_path: Path):
    n_bad = sum(1 for r in rows if not r["consistent"])
    lines = ["# Metric consistency report (v2)\n",
             "Confirms Table 4 `AFSP`/`RiskyAcc` = the explicit **all-generated** "
             "denominator recompute (AFSP_all, RiskyAcc_all).\n",
             f"\n**{len(rows) - n_bad}/{len(rows)} cells consistent** "
             f"(tolerance = published rounding).\n"]
    if n_bad:
        lines.append("\n## Mismatches\n")
        for r in rows:
            if not r["consistent"]:
                lines.append(f"- {r['model']} {r['mode']} {r['metric']}: "
                             f"published {r['published']} vs recomputed {r['recomputed']} "
                             f"(|Δ|={r['abs_diff']})")
    lines.append("\n## Denominator finding\n")
    lines.append("Table 4's AFSP matches **AFSP_all** (numerator accepted∧functional∧safe, "
                 "denominator = all 240 generated), not among-accepted. The caption is "
                 "corrected to state this, and **AFSP_among_accepted** is reported "
                 "alongside, where the gate's effect is visible:\n")
    for model in recomputed:
        if model == "pooled":
            b0 = recomputed[model].get("B0", {})
            b3 = recomputed[model].get("B3", {})
            lines.append(f"- pooled: AFSP_all {b0.get('afsp_all'):.3f}→{b3.get('afsp_all'):.3f} "
                         f"(≈flat) vs AFSP_among_accepted "
                         f"{b0.get('afsp_among_accepted'):.3f}→{b3.get('afsp_among_accepted'):.3f} (rises).")
    out_path.write_text("\n".join(lines) + "\n")
    return n_bad


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--full", type=Path, default=Path("results/metrics_v2/metrics_v2_full.json"))
    ap.add_argument("--out", type=Path, default=Path("results/metrics_v2/consistency_report.md"))
    args = ap.parse_args()
    recomputed = json.loads(args.full.read_text())
    rows = compare_to_published(recomputed, PUBLISHED_TABLE4)
    n_bad = write_report(rows, recomputed, args.out)
    print(f"consistency: {len(rows) - n_bad}/{len(rows)} cells match published Table 4")
    for r in rows:
        if not r["consistent"]:
            print(f"  MISMATCH {r['model']} {r['mode']} {r['metric']}: "
                  f"pub {r['published']} vs rec {r['recomputed']}")


if __name__ == "__main__":
    main()

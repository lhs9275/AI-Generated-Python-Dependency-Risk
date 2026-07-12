#!/usr/bin/env python3
"""Merge pass-1 and pass-2 ratings into results_test_retest.csv for compute_irr.py.

TEST-RETEST (intra-rater) reliability: the SAME author rated the samples twice,
separated by a washout period. This joins:
    pass 1  = rating_sheet_rater1.csv        -> rater1_* columns
    pass 2  = rating_sheet_pass2.csv          -> rater2_* columns
aligning by sample_id (pass 2 is row-shuffled, so we join on the key, not order),
and re-attaches the hidden stratification metadata + system oracle labels exactly
as merge_ratings.py does. compute_irr.py --mode test-retest then reports kappa
between the two passes as intra-rater agreement (NOT inter-rater).

Run:  python evaluation/manual_audit/merge_test_retest.py
Then: python evaluation/manual_audit/compute_irr.py \
          --input evaluation/manual_audit/results_test_retest.csv --mode test-retest
"""
import csv
import os

# Reuse the metadata join + system-label derivation from the inter-rater merger.
from merge_ratings import META, SAMPLE, _sys_labels

HERE = os.path.dirname(os.path.abspath(__file__))

PASS1 = os.path.join(HERE, "rating_sheet_rater1.csv")   # time 1 (already filled)
PASS2 = os.path.join(HERE, "rating_sheet_pass2.csv")     # time 2 (make_pass2_sheet.py)


def _load(path, label):
    if not os.path.exists(path):
        raise SystemExit(f"missing {path} — {label}")
    return {r["sample_id"]: r for r in csv.DictReader(open(path, encoding="utf-8-sig"))}


def main():
    p1 = _load(PASS1, "pass 1 (rating_sheet_rater1.csv)")
    p2 = _load(PASS2, "pass 2 — run make_pass2_sheet.py and have the author fill it")
    ids = sorted(set(p1) & set(p2))
    out, n_filled = [], 0
    for sid in ids:
        a, b, m = p1[sid], p2[sid], META.get(sid, {})
        if a.get("safety_pass_core", "").strip() and b.get("safety_pass_core", "").strip():
            n_filled += 1
        sys_spc, sys_unnec, sys_lic = _sys_labels(SAMPLE.get(sid, {}))
        out.append({
            "sample_id": sid, "task_id": m.get("task_id", ""),
            "family": m.get("family", ""), "guard_decision": m.get("guard_decision", ""),
            "strat_cell": m.get("strat_cell", ""),
            # pass 1 -> rater1_*, pass 2 -> rater2_*  (same author, two time points)
            "rater1_safety_pass_core": a.get("safety_pass_core", ""),
            "rater1_unnecessary_dep": a.get("unnecessary_dep", ""),
            "rater1_license_violation": a.get("license_violation", ""),
            "rater1_rationale": a.get("rationale", ""),
            "rater2_safety_pass_core": b.get("safety_pass_core", ""),
            "rater2_unnecessary_dep": b.get("unnecessary_dep", ""),
            "rater2_license_violation": b.get("license_violation", ""),
            "rater2_rationale": b.get("rationale", ""),
            "sys_safety_pass_core": sys_spc,
            "sys_unnecessary_dep": sys_unnec,
            "sys_license_violation": sys_lic,
        })
    cols = ["sample_id", "task_id", "family", "guard_decision", "strat_cell",
            "rater1_safety_pass_core", "rater1_unnecessary_dep", "rater1_license_violation", "rater1_rationale",
            "rater2_safety_pass_core", "rater2_unnecessary_dep", "rater2_license_violation", "rater2_rationale",
            "sys_safety_pass_core", "sys_unnecessary_dep", "sys_license_violation"]
    path = os.path.join(HERE, "results_test_retest.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in out:
            w.writerow(r)
    print(f"wrote {path}: {len(out)} rows, {n_filled} rated in BOTH passes")
    if n_filled < len(out):
        print(f"  ({len(out) - n_filled} rows missing a pass-2 answer — fill them before computing kappa)")
    print("next: python evaluation/manual_audit/compute_irr.py "
          "--input evaluation/manual_audit/results_test_retest.csv --mode test-retest")


if __name__ == "__main__":
    main()

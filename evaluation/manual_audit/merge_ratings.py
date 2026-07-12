#!/usr/bin/env python3
"""Merge the two filled blind rating sheets into results.csv for compute_irr.py.

Re-joins the hidden stratification metadata (family, guard_decision, strat_cell)
from sample_meta.json so compute_irr.py can do per-cell agreement. Run AFTER both
raters fill rating_sheet_rater{1,2}.csv.

Run:  python evaluation/manual_audit/merge_ratings.py
Then: python evaluation/manual_audit/compute_irr.py --input evaluation/manual_audit/results.csv
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
META = {e["sample_id"]: e for e in json.load(open(os.path.join(HERE, "sample_meta.json"), encoding="utf-8"))}
# sample.csv carries the ADJUDICATOR's SafetyPass-Core (the metric behind Tables 3-6) and the
# guard's detected risk labels, used as the system labels for oracle-validation.
SAMPLE = {r["sample_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "sample.csv"), encoding="utf-8-sig"))}


def _load(rater):
    p = os.path.join(HERE, f"rating_sheet_{rater}.csv")
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} — run make_rating_sheet.py and have {rater} fill it")
    return {r["sample_id"]: r for r in csv.DictReader(open(p, encoding="utf-8-sig"))}


def _sys_labels(srow):
    """SYSTEM labels for oracle-validation, each sourced to match what it actually validates:
      - safety_pass_core: the ADJUDICATOR's SafetyPass-Core (risk_oracle.yaml / safety_oracle —
        the ground truth behind RiskyAcc/SafetyPass-Core in Tables 3-6), read from sample.csv's
        safety_pass_core column. NOT the guard's risk_report.
      - unnecessary_dep (F6 / stage S6) and license_violation (F4 / stage S5): the GUARD's detected
        labels (risk_labels_detected), the relevant decision-maker for those stages.
    """
    spc = "yes" if (srow.get("safety_pass_core", "").strip().lower() in ("true", "1", "yes")) else "no"
    labels = srow.get("risk_labels_detected", "") or ""
    unnec = "yes" if "unnecessary_dependency" in labels else "no"
    if "license_blocked" in labels:
        lic = "yes"
    elif ("license_missing" in labels) or ("license_ambiguous" in labels):
        lic = "unclear"
    else:
        lic = "no"
    return spc, unnec, lic


def main():
    r1, r2 = _load("rater1"), _load("rater2")
    ids = sorted(set(r1) & set(r2))
    out, n_filled = [], 0
    for sid in ids:
        a, b, m = r1[sid], r2[sid], META.get(sid, {})
        if a.get("safety_pass_core", "").strip() and b.get("safety_pass_core", "").strip():
            n_filled += 1
        sys_spc, sys_unnec, sys_lic = _sys_labels(SAMPLE.get(sid, {}))
        out.append({
            "sample_id": sid, "task_id": m.get("task_id", ""),
            "family": m.get("family", ""), "guard_decision": m.get("guard_decision", ""),
            "strat_cell": m.get("strat_cell", ""),
            "rater1_safety_pass_core": a.get("safety_pass_core", ""),
            "rater1_unnecessary_dep": a.get("unnecessary_dep", ""),
            "rater1_license_violation": a.get("license_violation", ""),
            "rater1_rationale": a.get("rationale", ""),
            "rater2_safety_pass_core": b.get("safety_pass_core", ""),
            "rater2_unnecessary_dep": b.get("unnecessary_dep", ""),
            "rater2_license_violation": b.get("license_violation", ""),
            "rater2_rationale": b.get("rationale", ""),
            # system oracle labels (for oracle-validation, NOT shown to raters)
            "sys_safety_pass_core": sys_spc,
            "sys_unnecessary_dep": sys_unnec,
            "sys_license_violation": sys_lic,
        })
    cols = ["sample_id", "task_id", "family", "guard_decision", "strat_cell",
            "rater1_safety_pass_core", "rater1_unnecessary_dep", "rater1_license_violation", "rater1_rationale",
            "rater2_safety_pass_core", "rater2_unnecessary_dep", "rater2_license_violation", "rater2_rationale",
            "sys_safety_pass_core", "sys_unnecessary_dep", "sys_license_violation"]
    path = os.path.join(HERE, "results.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in out:
            w.writerow(r)
    print(f"wrote {path}: {len(out)} rows, {n_filled} fully rated by BOTH raters")
    if n_filled < len(out):
        print(f"  ({len(out) - n_filled} rows not yet rated by both — fill them before computing IRR)")
    print("next: python evaluation/manual_audit/compute_irr.py --input evaluation/manual_audit/results.csv")


if __name__ == "__main__":
    main()

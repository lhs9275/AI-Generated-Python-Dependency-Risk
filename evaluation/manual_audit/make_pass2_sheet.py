#!/usr/bin/env python3
"""Generate the BLIND second-pass sheet for TEST-RETEST (intra-rater) reliability.

A second independent rater is unavailable, so reliability is estimated by having
the SAME author re-annotate the same 60 F4/F6 samples after a washout period
(weeks), then comparing the two passes (Cohen's kappa). To curb recall/order
bias the second pass:
  * presents the SAME blinded context columns as pass 1 (no guard decision / no
    system label / no pass-1 answer is shown), and
  * SHUFFLES the row order with a fixed seed so items are not encountered in the
    pass-1 sequence.

Output: rating_sheet_pass2.csv  (same input schema as rating_sheet_rater1.csv;
        rating cells blank for the author to fill at time 2).

Run:  python evaluation/manual_audit/make_pass2_sheet.py
Then (after the author fills it):
      python evaluation/manual_audit/merge_test_retest.py
      python evaluation/manual_audit/compute_irr.py \
          --input evaluation/manual_audit/results_test_retest.csv --mode test-retest
"""
import argparse
import csv
import json
import os
import random

from make_rating_sheet import task_requirement  # reuse the same blinded excerpt logic

HERE = os.path.dirname(os.path.abspath(__file__))
META = os.path.join(HERE, "sample_meta.json")

# Fixed seed -> reproducible shuffle. Distinct from the natural S001..S060 order
# of pass 1 so the author does not re-encounter items in the same sequence.
DEFAULT_SEED = 20260603


def build_rows():
    meta = json.load(open(META, encoding="utf-8"))
    rows = []
    for e in meta:
        deps = e.get("dep_changes", [])
        rows.append({
            "sample_id": e["sample_id"],
            "family": e["family"],                         # F4=license, F6=unnecessary-dep
            "condition": e.get("condition", ""),
            "added_packages": ", ".join(d["package"] for d in deps),
            "dependency_change": " | ".join(
                f'{d.get("new_line") or d["package"]} [{d.get("file", "?")}]' for d in deps),
            "task_requirement": task_requirement(e["task_id"]),
            # ---- author fills these at time 2 (everything else is read-only context) ----
            "safety_pass_core": "",      # ALL rows: yes / no / unclear
            "unnecessary_dep": "",       # F6 rows ONLY: yes / no / unclear (blank for F4)
            "license_violation": "",     # F4 rows ONLY: yes / no / unclear (blank for F6)
            "rationale": "",
        })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help="shuffle seed for the second-pass row order")
    ap.add_argument("--out", default=os.path.join(HERE, "rating_sheet_pass2.csv"))
    args = ap.parse_args()

    rows = build_rows()
    random.Random(args.seed).shuffle(rows)

    cols = ["sample_id", "family", "condition", "added_packages", "dependency_change",
            "task_requirement", "safety_pass_core", "unnecessary_dep", "license_violation",
            "rationale"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    n4 = sum(r["family"] == "F4" for r in rows)
    n6 = sum(r["family"] == "F6" for r in rows)
    print(f"wrote {args.out}")
    print(f"{len(rows)} blinded samples (F4={n4}, F6={n6}), order shuffled (seed={args.seed}).")
    print("System decision/labels and pass-1 answers are HIDDEN. Fill at time 2, then run "
          "merge_test_retest.py.")


if __name__ == "__main__":
    main()

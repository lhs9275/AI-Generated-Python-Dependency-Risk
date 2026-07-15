#!/usr/bin/env bash
# ============================================================================
# NOTE (r7+): This script reproduces the PRE-CORRECTION (r5) naturalistic
# baseline — primary 328/8,752 = 3.7% with the original P3 adjudication. That
# baseline is SUPERSEDED by the P3 affected-range re-verification (Section
# "correction"): the manuscript's current result is 279/8,752 = 3.19%.
# This script is retained ONLY to prove the raw parse (its 328 reproduction is
# what validates the correction's starting point). For the CORRECTED manuscript
# numbers and CIs run instead:
#   python results/major_revision/results_recompute.py
#   python results/major_revision/prevalence_cluster_ci_corrected.py
# See results/major_revision/CORRECTION_NOTICE.md.
# ============================================================================
# Reproduce the naturalistic validation (Table VI) and the inter-labeler
# agreement (primary Cohen kappa) entirely offline from the archived per-change
# corpus. No GPU and no network required:
#   - the gate ladder (Table VI) is recomputed from the frozen guard decisions
#     (guard_outputs.jsonl) joined to the independent gold labels;
#   - the primary kappa is RECOMPUTED from the two labelers' raw label files
#     (labels_A.csv vs labels_B.csv) over the post-exclusion change set, and
#     hard-asserted against the archived value (not merely echoed).
#
# Usage:  ./scripts/reproduce_naturalistic.sh
set -euo pipefail
cd "$(dirname "$0")/.."

DATA=results/tse_gap_closure/data
REF=results/tse_gap_closure/analysis
OUT=results/tse_gap_closure/analysis_recomputed

echo "== Recomputing naturalistic gate ladder (Table VI) from archived files =="
python3 -m pipeline.tse_gap_closure.analyze \
  --labels "$DATA/independent_labels.csv" \
  --guard  "$DATA/guard_outputs.jsonl" \
  --out-dir "$OUT"

echo
echo "== Cross-check recomputed Table VI vs archived reference =="
if diff <(sort "$REF/naturalistic_validation_summary.csv") \
        <(sort "$OUT/naturalistic_validation_summary.csv") >/dev/null; then
  echo "Table VI: recomputed == archived  ✓"
else
  echo "Table VI: MISMATCH vs archived  ✗"; exit 1
fi

echo
echo "== Inter-labeler agreement: RECOMPUTING primary Cohen kappa from raw labels =="
python3 - "$DATA" <<'PY'
import csv, json, sys
from collections import Counter
D = sys.argv[1]

def load(fn):
    m = {}
    with open(f"{D}/{fn}", newline="") as fh:
        for r in csv.DictReader(fh):
            m[r["change_id"]] = r["label_primary"]
    return m

A = load("labels_A.csv")
B = load("labels_B.csv")

# The post-exclusion labeling target is the merged change set (extraction noise
# dropped); independent_labels.csv enumerates exactly those change_ids.
keep = []
with open(f"{D}/independent_labels.csv", newline="") as fh:
    for r in csv.DictReader(fh):
        cid = r["change_id"]
        if cid in A and cid in B:
            keep.append(cid)

a = [A[c] for c in keep]
b = [B[c] for c in keep]
n = len(keep)
cats = sorted(set(a) | set(b))
po = sum(1 for x, y in zip(a, b) if x == y) / n          # observed agreement
ca, cb = Counter(a), Counter(b)
pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)        # chance agreement
kappa = (po - pe) / (1 - pe)                             # Cohen kappa

ref = json.load(open(f"{D}/labeling_agreement.json"))
print(f"recomputed: n_changes={n}  agreement={po:.4f}  primary Cohen kappa={kappa:.4f}")
print(f"archived  : n_changes={ref['n_changes']}  agreement={ref['primary_agreement_rate']:.4f}  "
      f"primary Cohen kappa={ref['primary_kappa']:.4f}  (adjudicated {ref['n_adjudicated']})")
assert n == ref["n_changes"], f"n mismatch: {n} != {ref['n_changes']}"
assert abs(kappa - ref["primary_kappa"]) < 5e-4, f"kappa mismatch: {kappa} != {ref['primary_kappa']}"
print("kappa: recomputed == archived  ✓  (manuscript rounds primary kappa to 0.90)")
PY

echo
echo "== Prevalence point estimate and 95% CIs (Section IV / abstract) =="
python3 -m pipeline.tse_gap_closure.prevalence_cluster_ci \
  --labels "$DATA/independent_labels.csv" --out-dir "$OUT"
python3 - "$OUT" <<'PY'
import json, sys
o = json.load(open(f"{sys.argv[1]}/prevalence_cluster_ci.json"))
# Fixed-seed percentile bootstrap => byte-deterministic endpoints, so the
# manuscript's stated CIs are hard-asserted (not merely echoed).
ci = o["ci_95_pct"]
assert o["point"]["k"] == 328 and o["point"]["n"] == 8752, "prevalence counts drift"
assert ci["wilson_unclustered"] == [3.37, 4.17], ci["wilson_unclustered"]
assert ci["pr_clustered"] == [2.96, 4.68], ci["pr_clustered"]
assert ci["repo_clustered"] == [2.94, 4.7], ci["repo_clustered"]
print("prevalence CIs: recomputed == r5 PRE-CORRECTION baseline  ✓  "
      "(3.7% 328/8752; Wilson 3.4-4.2; PR-clustered 2.96-4.68; "
      "repo-clustered 2.94-4.70). SUPERSEDED by 3.19% 279/8752 — see "
      "results/major_revision/ (CORRECTION_NOTICE.md).")
PY

echo
echo "Done. Recomputed Table VI is under $OUT/ and the primary kappa was"
echo "re-derived from the raw labeler files; both match the manuscript."

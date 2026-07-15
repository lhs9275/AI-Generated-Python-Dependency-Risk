"""Corrected-label variant of the canonical prevalence cluster-bootstrap CI.

Reuses the EXACT canonical functions (cluster_bootstrap, cluster_counts) from
pipeline.tse_gap_closure.prevalence_cluster_ci so the method is byte-identical to
the paper's 60,000-resample seed-42 procedure; only the labels differ (the P3
affected-range correction from changed_rows_final.csv is applied first). Emits the
corrected point estimate + Wilson/PR-clustered/repo-clustered 95% CIs and archives
them for r6. Run from the artifact root:

    python -m results.major_revision.prevalence_cluster_ci_corrected
"""
import csv, json
from pathlib import Path
from statsmodels.stats.proportion import proportion_confint
from pipeline.tse_gap_closure.prevalence_cluster_ci import (
    cluster_bootstrap, CHANGE_TYPES, SEED, N_BOOTSTRAP,
)

LABELS = "results/tse_gap_closure/data/independent_labels.csv"
CHANGED = "results/major_revision/changed_rows_final.csv"
OUT = "results/major_revision/prevalence_cluster_ci_corrected.json"
EXPECT_N = 8752
EXPECT_K = 279  # corrected primary count (was 328)

# corrected-label overrides
changed = {}
with open(CHANGED, newline="") as fh:
    for r in csv.DictReader(fh):
        changed[r["change_id"]] = r["new_label"]

def corrected_label(r):
    return changed.get(r["change_id"], r["label_primary"])

rows = []
with open(LABELS, newline="") as fh:
    for r in csv.DictReader(fh):
        if r["change_type"] in CHANGE_TYPES:
            r["label_primary"] = corrected_label(r)  # apply correction in place
            rows.append(r)

n = len(rows)
k = sum(1 for r in rows if r["label_primary"] != "NONE")
assert n == EXPECT_N, f"denominator {n} != {EXPECT_N}"
assert k == EXPECT_K, f"corrected risk count {k} != {EXPECT_K}"

# cluster_counts keys off label_primary=='NONE'; build ks/ns per cluster
from collections import defaultdict
def cluster_counts(rows, key):
    g = defaultdict(lambda: [0, 0])
    for r in rows:
        cell = g[r[key]]
        cell[0] += 0 if r["label_primary"] == "NONE" else 1
        cell[1] += 1
    return [v[0] for v in g.values()], [v[1] for v in g.values()], len(g)

wlo, whi = proportion_confint(k, n, alpha=0.05, method="wilson")
pr_ks, pr_ns, pr_C = cluster_counts(rows, "pr_id")
repo_ks, repo_ns, repo_C = cluster_counts(rows, "repo")
pr_lo, pr_hi = cluster_bootstrap(pr_ks, pr_ns, SEED, N_BOOTSTRAP)
repo_lo, repo_hi = cluster_bootstrap(repo_ks, repo_ns, SEED, N_BOOTSTRAP)

out = {
    "corrected": True,
    "point": {"k": k, "n": n, "rate_pct": round(100 * k / n, 2),
              "n_prs": pr_C, "n_repos": repo_C},
    "method": {"seed": SEED, "n_bootstrap": N_BOOTSTRAP, "resample": "percentile",
               "change_types": list(CHANGE_TYPES),
               "labels_applied": "changed_rows_final.csv (55 FP->NONE, 6 FN->P3)"},
    "ci_95_pct": {
        "wilson_unclustered": [round(100 * wlo, 2), round(100 * whi, 2)],
        "pr_clustered": [pr_lo, pr_hi],
        "repo_clustered": [repo_lo, repo_hi],
    },
}
Path(OUT).write_text(json.dumps(out, indent=2))
print(f"corrected point = {k}/{n} = {100*k/n:.2f}%  ({pr_C} PRs, {repo_C} repos)")
print(f"Wilson         95% CI = {100*wlo:.2f}-{100*whi:.2f}%")
print(f"PR-clustered   95% CI = {pr_lo}-{pr_hi}%  (seed {SEED}, {N_BOOTSTRAP})")
print(f"repo-clustered 95% CI = {repo_lo}-{repo_hi}%  (seed {SEED}, {N_BOOTSTRAP})")
print(f"wrote {OUT}")

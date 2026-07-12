"""Reproduce the naturalistic primary-risk prevalence point estimate and its
confidence intervals entirely offline from the archived per-change gold labels.

Emits three 95% CIs for the 3.7% (328/8,752) headline:
  * unclustered Wilson (statsmodels),
  * PR-clustered cluster bootstrap,
  * repository-clustered cluster bootstrap,
both bootstraps at 60,000 percentile resamples with a fixed seed so the endpoints
are byte-deterministic across machines and Monte-Carlo-stable to two decimals.
Determinism: numpy PCG64 via default_rng(42); Generator.integers (Lemire) and the
PCG64 raw stream have been stable since numpy 1.17; percentiles use the explicit
"linear" interpolation; bootstrap rates are ratios of exact integer sums (< 2^53,
bit-exact). The reproduction script hard-asserts the emitted endpoints, so any
future RNG-stream change fails loudly rather than drifting silently.

This is the recompute behind the abstract/Section IV CI numbers; it reads no GPU
and no network, only results/tse_gap_closure/data/independent_labels.csv.

Usage:
    python -m pipeline.tse_gap_closure.prevalence_cluster_ci \
        --labels results/tse_gap_closure/data/independent_labels.csv \
        --out-dir results/tse_gap_closure/analysis_recomputed
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from statsmodels.stats.proportion import proportion_confint

# The prevalence denominator is dependency introductions and version changes
# (removes are not a supply-chain-introduction decision).
CHANGE_TYPES = ("add", "version_change")
SEED = 42
N_BOOTSTRAP = 60000
# Resamples are generated in chunks so peak memory stays ~50 MB even at 60k
# clusters; the PCG64 stream is position-based, so chunked draws are bit-identical
# to a single (n_boot, C) draw.
BOOT_CHUNK = 5000
# Hard invariant: the archived label set must yield exactly the paper's counts.
EXPECT_N = 8752
EXPECT_K = 328


def load_subset(path):
    rows = []
    with open(path, newline="") as fh:
        for r in csv.DictReader(fh):
            if r["change_type"] in CHANGE_TYPES:
                rows.append(r)
    return rows


def cluster_bootstrap(ks, ns, seed=SEED, n_boot=N_BOOTSTRAP, chunk=BOOT_CHUNK):
    """Percentile cluster bootstrap: resample whole clusters with replacement.

    Chunked to cap peak memory; bit-identical to a single (n_boot, C) draw.
    """
    ks = np.asarray(ks, float)
    ns = np.asarray(ns, float)
    C = len(ks)
    rng = np.random.default_rng(seed)
    rates = np.empty(n_boot)
    done = 0
    while done < n_boot:
        m = min(chunk, n_boot - done)
        idx = rng.integers(0, C, size=(m, C))
        rates[done:done + m] = ks[idx].sum(axis=1) / ns[idx].sum(axis=1)
        done += m
    lo, hi = np.percentile(rates, [2.5, 97.5], method="linear")
    return round(100 * lo, 2), round(100 * hi, 2)


def cluster_counts(rows, key):
    g = defaultdict(lambda: [0, 0])  # key -> [risks, changes]
    for r in rows:
        cell = g[r[key]]
        cell[0] += 0 if r["label_primary"] == "NONE" else 1
        cell[1] += 1
    ks = [v[0] for v in g.values()]
    ns = [v[1] for v in g.values()]
    return ks, ns, len(g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels",
                    default="results/tse_gap_closure/data/independent_labels.csv")
    ap.add_argument("--out-dir",
                    default="results/tse_gap_closure/analysis_recomputed")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    args = ap.parse_args()

    rows = load_subset(args.labels)
    n = len(rows)
    k = sum(1 for r in rows if r["label_primary"] != "NONE")
    assert n == EXPECT_N, f"denominator {n} != expected {EXPECT_N}"
    assert k == EXPECT_K, f"risk count {k} != expected {EXPECT_K}"

    wlo, whi = proportion_confint(k, n, alpha=0.05, method="wilson")
    pr_ks, pr_ns, pr_C = cluster_counts(rows, "pr_id")
    repo_ks, repo_ns, repo_C = cluster_counts(rows, "repo")
    pr_lo, pr_hi = cluster_bootstrap(pr_ks, pr_ns, args.seed, args.n_bootstrap)
    repo_lo, repo_hi = cluster_bootstrap(repo_ks, repo_ns, args.seed, args.n_bootstrap)

    out = {
        "point": {"k": k, "n": n, "rate_pct": round(100 * k / n, 2),
                  "n_prs": pr_C, "n_repos": repo_C},
        "method": {"seed": args.seed, "n_bootstrap": args.n_bootstrap,
                   "resample": "percentile", "change_types": list(CHANGE_TYPES)},
        "ci_95_pct": {
            "wilson_unclustered": [round(100 * wlo, 2), round(100 * whi, 2)],
            "pr_clustered": [pr_lo, pr_hi],
            "repo_clustered": [repo_lo, repo_hi],
        },
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prevalence_cluster_ci.json").write_text(json.dumps(out, indent=2))

    print(f"point prevalence = {k}/{n} = {100 * k / n:.2f}%  "
          f"({pr_C} PRs, {repo_C} repos)")
    print(f"Wilson (unclustered)  95% CI = {100 * wlo:.2f}-{100 * whi:.2f}%")
    print(f"PR-clustered   bootstrap CI = {pr_lo}-{pr_hi}%  "
          f"(seed={args.seed}, {args.n_bootstrap} resamples)")
    print(f"repo-clustered bootstrap CI = {repo_lo}-{repo_hi}%  "
          f"(seed={args.seed}, {args.n_bootstrap} resamples)")
    print(f"wrote {out_dir / 'prevalence_cluster_ci.json'}")


if __name__ == "__main__":
    main()

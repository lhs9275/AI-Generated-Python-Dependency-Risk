"""
Sensitivity analysis for the primary B0 (no gate) vs B3 (full guard) comparison
on both RiskyAcc-All (F1-F6) and RiskyAcc-Core (F1-F3). In both endpoints the
outcome is whether an accepted patch still contains oracle risk; Core is formed
by restricting the canonical runs to task families F1-F3, not by changing the
accepted-patch outcome definition.

The headline result is reported with paired McNemar p, Cohen's h and Haldane odds
ratios in the manuscript. A reviewer asked for the primary effect to be
re-confirmed with two analyses that respect the paired/clustered structure:

  1. Family-stratified task-clustered bootstrap of each RiskyAcc risk difference
     (B3 - B0) and its 95% CI, per model AND pooled across all 5 models. We
     resample UNIQUE TASK IDs within task family (NOT individual runs or
     model-task cells); a pooled sampled task carries all five models, G0/G1,
     and both gate modes. An unstratified unique-task interval is also emitted.

  2. Marginal GEE logistic regression predicting risky_accepted (0/1) from gate
     mode (B0 vs B3), with exchangeable correlation and robust sandwich SEs
     grouped by the shared task_id. The five evaluated models and two generation
     conditions form a fixed, balanced panel within each task.

The paired unit for B0-vs-B3 is the RUN (same generation fixed, gate mode varies).
Pooling G0+G1 gives 240 runs/model for All and 120 runs/model for Core. The
legacy RiskyAcc-All JSON keys are preserved; Core results are added under
``bootstrap_risk_diff_core`` and ``clustered_logistic_core``.

Output: results/sensitivity_analysis.json
Run:    python pipeline/sensitivity_analysis.py
"""

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.compute_tse_stats import collect_runs, mode_val, MODEL_DISPLAY

MODEL_ORDER = ["Qwen-7B", "Qwen-14B", "Qwen-32B", "DeepSeek-6.7B", "CodeLlama-7B"]
CORE_FAMILIES = frozenset({"F1", "F2", "F3"})

SEED = 12345
N_BOOTSTRAP = 10000


# ── data assembly ────────────────────────────────────────────────────────────

def build_long_frame(results_dir: Path, runs_jsonl: Path | None = None) -> pd.DataFrame:
    """One row per (model, run, gate_mode). Each run contributes a B0 row and a
    B3 row, both carrying the same task_id (the bootstrap cluster) and the same
    model. `risky` is the RiskyAcc-All indicator (1 = an accepted patch still
    contained F1-F6 oracle risk). ``task_family`` is parsed from the canonical
    ``task_F*_NNN`` identifier so Core can be selected explicitly as F1-F3."""
    rows = []
    for slug, display in MODEL_DISPLAY.items():
        runs = collect_runs(results_dir, slug, runs_jsonl=runs_jsonl)
        for i, r in enumerate(runs):
            task_id = r["task_id"]
            task_id_parts = str(task_id).split("_")
            task_family = (
                task_id_parts[1]
                if len(task_id_parts) >= 3 and task_id_parts[0] == "task"
                else None
            )
            cond = r["generation_condition"]
            # stable per-run id so B0/B3 of the same run pair correctly
            run_id = f"{display}|{task_id}|{cond}|{i}"
            for mode in ("B0", "B3"):
                v = mode_val(r, mode, "accepted", "risky_accepted_patch")
                if v is None:
                    continue
                rows.append({
                    "model": display,
                    "task_id": task_id,
                    "task_family": task_family,
                    "cond": cond,
                    "run_id": run_id,
                    "mode": mode,
                    "risky": 1 if v else 0,
                })
    df = pd.DataFrame(rows)
    return df


def core_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return RiskyAcc-Core rows: accepted-patch risk on F1-F3 tasks only."""
    if "task_family" not in df.columns:
        raise ValueError("long frame is missing task_family; rebuild with build_long_frame")
    return df[df["task_family"].isin(CORE_FAMILIES)].copy()


# ── 1. task-clustered bootstrap ──────────────────────────────────────────────

def _rates_from_subset(sub: pd.DataFrame):
    """Return (b0_rate, b3_rate, diff) for a long subframe with mode/risky cols."""
    b0 = sub[sub["mode"] == "B0"]["risky"]
    b3 = sub[sub["mode"] == "B3"]["risky"]
    if len(b0) == 0 or len(b3) == 0:
        return None, None, None
    b0_rate = b0.mean()
    b3_rate = b3.mean()
    return float(b0_rate), float(b3_rate), float(b3_rate - b0_rate)


def _cluster_arrays(df: pd.DataFrame):
    """Precompute outcome counts per shared task_id cluster.

    In a per-model frame a task contains G0/G1 and B0/B3. In the pooled frame
    it additionally contains all five models. Those model rows must stay
    together because every model saw the same benchmark stimulus.

    Returns dict: task_id -> (b0_n, b0_risky, b3_n, b3_risky)."""
    is_b0 = (df["mode"] == "B0").to_numpy()
    is_b3 = (df["mode"] == "B3").to_numpy()
    risky = df["risky"].to_numpy()
    out = {}
    for key, idx in df.groupby("task_id", sort=False).indices.items():
        sel0 = is_b0[idx]
        sel3 = is_b3[idx]
        rk = risky[idx]
        out[key] = (
            int(sel0.sum()),
            int((rk * sel0).sum()),
            int(sel3.sum()),
            int((rk * sel3).sum()),
        )
    return out


def _boot_diffs(cluster_arrays, keys, rng, n_boot):
    """Vectorized task-clustered bootstrap of the RiskyAcc difference (B3 - B0).

    For each cluster we have (b0_n, b0_risky, b3_n, b3_risky). A bootstrap
    resample draws len(keys) clusters with replacement; the resampled B0 rate is
    sum(b0_risky)/sum(b0_n) over drawn clusters, likewise B3; diff = B3 - B0.
    All n_boot samples are computed with numpy take + matrix sum (no loop)."""
    arr = np.array([cluster_arrays[k] for k in keys], dtype=float)  # (K, 4)
    K = arr.shape[0]
    b0_n, b0_r, b3_n, b3_r = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]
    picks = rng.integers(0, K, size=(n_boot, K))  # (n_boot, K) cluster indices
    sum_b0_n = b0_n[picks].sum(axis=1)
    sum_b0_r = b0_r[picks].sum(axis=1)
    sum_b3_n = b3_n[picks].sum(axis=1)
    sum_b3_r = b3_r[picks].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        b0_rate = sum_b0_r / sum_b0_n
        b3_rate = sum_b3_r / sum_b3_n
    diffs = b3_rate - b0_rate
    diffs = diffs[np.isfinite(diffs)]
    return diffs


def _boot_diffs_stratified(cluster_arrays, strata, rng, n_boot):
    """Resample unique tasks within each pre-specified task-family stratum."""
    sum_b0_n = np.zeros(n_boot, dtype=float)
    sum_b0_r = np.zeros(n_boot, dtype=float)
    sum_b3_n = np.zeros(n_boot, dtype=float)
    sum_b3_r = np.zeros(n_boot, dtype=float)

    for keys in strata:
        arr = np.array([cluster_arrays[k] for k in keys], dtype=float)
        K = arr.shape[0]
        picks = rng.integers(0, K, size=(n_boot, K))
        sum_b0_n += arr[:, 0][picks].sum(axis=1)
        sum_b0_r += arr[:, 1][picks].sum(axis=1)
        sum_b3_n += arr[:, 2][picks].sum(axis=1)
        sum_b3_r += arr[:, 3][picks].sum(axis=1)

    with np.errstate(invalid="ignore", divide="ignore"):
        diffs = (sum_b3_r / sum_b3_n) - (sum_b0_r / sum_b0_n)
    return diffs[np.isfinite(diffs)]


def _family_strata(df: pd.DataFrame, keys):
    """Return task-id lists by family, preserving the benchmark strata."""
    task_family = df[["task_id", "task_family"]].drop_duplicates()
    if task_family["task_id"].duplicated().any():
        raise ValueError("a task_id maps to more than one task_family")
    family_by_task = dict(zip(task_family["task_id"], task_family["task_family"]))
    by_family = {}
    for key in keys:
        by_family.setdefault(family_by_task.get(key), []).append(key)
    return [by_family[f] for f in sorted(by_family, key=lambda x: str(x))]


def task_clustered_bootstrap(df: pd.DataFrame, rng: np.random.Generator,
                             n_boot: int = N_BOOTSTRAP):
    """Resample unique task IDs and recompute the paired B3-B0 risk difference.

    The primary percentile interval is stratified by task family because the
    benchmark fixes an equal number of tasks in every family. A non-stratified
    unique-task interval is returned alongside it. For the pooled analysis, a
    sampled task carries all five models; tasks, not model-task cells, are the
    generalization unit.
    """
    out = {}

    def summarize(point_df, keys, diffs, diffs_unstratified):
        b0_rate, b3_rate, diff = _rates_from_subset(point_df)
        return {
            "b0_risky_rate": round(b0_rate, 6),
            "b3_risky_rate": round(b3_rate, 6),
            "risk_diff": round(diff, 6),
            "bootstrap_ci_lo": round(float(np.percentile(diffs, 2.5)), 6),
            "bootstrap_ci_hi": round(float(np.percentile(diffs, 97.5)), 6),
            "bootstrap_mean": round(float(diffs.mean()), 6),
            "bootstrap_method": (
                "family-stratified percentile bootstrap over unique task_id "
                "clusters; a sampled task carries all model/condition/mode rows"
            ),
            "unstratified_ci_lo": round(
                float(np.percentile(diffs_unstratified, 2.5)), 6),
            "unstratified_ci_hi": round(
                float(np.percentile(diffs_unstratified, 97.5)), 6),
            "unstratified_mean": round(float(diffs_unstratified.mean()), 6),
            "n_tasks": int(len(keys)),
            "n_task_model_cells": int(
                point_df[["model", "task_id"]].drop_duplicates().shape[0]),
            "n_runs": int(point_df[point_df["mode"] == "B0"].shape[0]),
        }

    # per-model
    for model in MODEL_ORDER:
        mdf = df[df["model"] == model]
        if mdf.empty:
            continue
        cluster_arrays = _cluster_arrays(mdf)
        keys = list(cluster_arrays)
        strata = _family_strata(mdf, keys)
        diffs = _boot_diffs_stratified(cluster_arrays, strata, rng, n_boot)
        diffs_unstratified = _boot_diffs(cluster_arrays, keys, rng, n_boot)
        out[model] = summarize(mdf, keys, diffs, diffs_unstratified)

    # Pooled over the fixed five-model panel: a task draw retains every model.
    cluster_arrays = _cluster_arrays(df)
    all_keys = list(cluster_arrays.keys())
    strata = _family_strata(df, all_keys)
    diffs = _boot_diffs_stratified(cluster_arrays, strata, rng, n_boot)
    diffs_unstratified = _boot_diffs(cluster_arrays, all_keys, rng, n_boot)
    out["Pooled"] = summarize(df, all_keys, diffs, diffs_unstratified)
    return out


# ── 2. mixed / GEE clustered logistic ────────────────────────────────────────

def clustered_logistic(df: pd.DataFrame):
    """Predict risky (0/1) from gate mode (B0 vs B3) respecting clustering.

    The estimand is the marginal B3-vs-B0 odds ratio over the balanced, fixed
    five-model/two-condition evaluation panel. GEE groups by the shared task_id,
    so all repeated outcomes for the same benchmark stimulus remain in one
    cluster. Robust sandwich standard errors account for within-task dependence.
    """
    from statsmodels.genmod.generalized_estimating_equations import GEE
    from statsmodels.genmod.cov_struct import Exchangeable
    from statsmodels.genmod.families import Binomial

    d = df.copy()
    # gate: 0 = B0 (reference), 1 = B3
    d["gate_b3"] = (d["mode"] == "B3").astype(int)
    d["cluster"] = d["task_id"].astype(str)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = GEE.from_formula(
                "risky ~ gate_b3", groups="cluster", data=d,
                cov_struct=Exchangeable(), family=Binomial())
            res = model.fit(maxiter=200)
        if not bool(getattr(res, "converged", False)):
            return {
                "method_used": "NONE — GEE logistic did not converge",
                "b3_coef": None, "odds_ratio": None,
                "or_ci_lo": None, "or_ci_hi": None, "p_value": None,
                "n_obs": int(d.shape[0]),
                "n_clusters": int(d["cluster"].nunique()),
                "converged": False,
                "convergence_notes": (
                    "GEE fit returned without an exception but did not report "
                    "convergence; inferential estimates are therefore omitted."
                ),
            }

        coef = float(res.params["gate_b3"])
        ci = res.conf_int().loc["gate_b3"]
        lo, hi = float(ci[0]), float(ci[1])
        p = float(res.pvalues["gate_b3"])
        return {
            "method_used": (
                "GEE logistic (Binomial family, exchangeable working correlation, "
                "groups=shared task_id); marginal B3-vs-B0 effect over the fixed "
                "five-model, two-generation-condition evaluation panel"
            ),
            "b3_coef": round(coef, 6),
            "odds_ratio": round(float(np.exp(coef)), 6),
            "or_ci_lo": round(float(np.exp(lo)), 6),
            "or_ci_hi": round(float(np.exp(hi)), 6),
            "p_value": p,
            "n_obs": int(d.shape[0]),
            "n_clusters": int(d["cluster"].nunique()),
            "converged": True,
            "convergence_notes": (
                "GEE converged (cov_struct=Exchangeable); robust sandwich SEs "
                "over unique task_id clusters. "
                "OR is B3 vs B0 (B0 = reference); OR << 1 means B3 sharply "
                "reduces the odds of an accepted-but-risky patch. Consistent in "
                "direction and magnitude with the paired McNemar / Haldane OR "
                "result reported in the manuscript."),
        }
    except Exception as e:  # noqa: BLE001
        return {
            "method_used": "NONE — GEE logistic failed",
            "b3_coef": None, "odds_ratio": None,
            "or_ci_lo": None, "or_ci_hi": None, "p_value": None,
            "n_obs": int(d.shape[0]),
            "n_clusters": int(d["cluster"].nunique()),
            "converged": False,
            "convergence_notes": f"GEE logistic failed: {type(e).__name__}: {e}",
        }


# ── main ──────────────────────────────────────────────────────────────────────

def run(
    results_dir: Path,
    n_boot: int = N_BOOTSTRAP,
    seed: int = SEED,
    runs_jsonl: Path | None = None,
):
    df = build_long_frame(results_dir, runs_jsonl=runs_jsonl)

    # sanity: pooled rates
    pooled_b0 = df[df["mode"] == "B0"]["risky"].mean()
    pooled_b3 = df[df["mode"] == "B3"]["risky"].mean()
    if not (abs(pooled_b0 - 0.253) < 0.01 and abs(pooled_b3 - 0.025) < 0.01):
        raise SystemExit(
            f"SANITY FAIL: pooled B0={pooled_b0:.3f} (exp ~0.253), "
            f"B3={pooled_b3:.3f} (exp ~0.025) — mis-collected runs; investigate.")

    core = core_frame(df)
    if core.empty:
        raise SystemExit("SANITY FAIL: no F1-F3 rows available for RiskyAcc-Core")

    # Give each endpoint the same fixed RNG seed so All/Core are reproducible
    # independently of one another.
    bootstrap = task_clustered_bootstrap(
        df, np.random.default_rng(seed), n_boot=n_boot)
    bootstrap_core = task_clustered_bootstrap(
        core, np.random.default_rng(seed), n_boot=n_boot)
    logistic = clustered_logistic(df)
    logistic_core = clustered_logistic(core)

    return {
        "config": {
            "seed": seed,
            "n_bootstrap": n_boot,
            "cluster": (
                "unique task_id; pooled task clusters retain all five models, "
                "both generation conditions, and paired B0/B3 rows"
            ),
            "bootstrap": (
                "family-stratified unique-task percentile bootstrap; "
                "unstratified unique-task interval also reported"
            ),
            "paired_unit": "run (gate mode varies within a run; G0+G1 pooled)",
            "outcome": "risky_accepted_patch (RiskyAcc-All)",
            "core_outcome": (
                "accepted.risky_accepted_patch restricted to task families "
                "F1-F3 (RiskyAcc-Core)"
            ),
        },
        "bootstrap_risk_diff": bootstrap,
        "clustered_logistic": logistic,
        "bootstrap_risk_diff_core": bootstrap_core,
        "clustered_logistic_core": logistic_core,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", type=Path, default=Path("results"))
    ap.add_argument("--runs-jsonl", type=Path, default=None)
    ap.add_argument("--output-json", type=Path,
                    default=Path("results/sensitivity_analysis.json"))
    ap.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    print(f"Collecting runs and running sensitivity analysis "
          f"(seed={args.seed}, n_boot={args.n_bootstrap})...")
    result = run(
        args.results_dir,
        n_boot=args.n_bootstrap,
        seed=args.seed,
        runs_jsonl=args.runs_jsonl,
    )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Wrote {args.output_json}\n")

    # ── summary ──
    for endpoint, bs_key, logistic_key in (
        ("RiskyAcc-All", "bootstrap_risk_diff", "clustered_logistic"),
        ("RiskyAcc-Core (F1-F3)", "bootstrap_risk_diff_core", "clustered_logistic_core"),
    ):
        print(f"=== Task-clustered bootstrap: {endpoint} "
              "risk difference (B3 - B0) ===")
        print(f"{'Group':14s} {'B0':>7s} {'B3':>7s} {'Diff(pp)':>9s} "
              f"{'95% CI (pp)':>20s} {'nTask':>6s} {'nRun':>6s}")
        bs = result[bs_key]
        for g in MODEL_ORDER + ["Pooled"]:
            if g not in bs:
                continue
            d = bs[g]
            print(f"{g:14s} {100*d['b0_risky_rate']:6.1f}% "
                  f"{100*d['b3_risky_rate']:6.1f}% "
                  f"{100*d['risk_diff']:+8.1f} "
                  f"[{100*d['bootstrap_ci_lo']:+6.1f}, "
                  f"{100*d['bootstrap_ci_hi']:+6.1f}] "
                  f"{d['n_tasks']:6d} {d['n_runs']:6d}")

        print(f"\n=== Clustered logistic: {endpoint} (B3 vs B0) ===")
        lg = result[logistic_key]
        print(f"method : {lg['method_used']}")
        if lg["odds_ratio"] is not None:
            print(f"coef   : {lg['b3_coef']:.4f} (log-odds)")
            print(f"OR     : {lg['odds_ratio']:.4f}  "
                  f"95% CI [{lg['or_ci_lo']:.4f}, {lg['or_ci_hi']:.4f}]")
            print(f"p      : {lg['p_value']:.3e}")
        print(f"notes  : {lg['convergence_notes']}\n")


if __name__ == "__main__":
    main()

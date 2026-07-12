"""
Workstream H — controlled-benchmark, ablation, and repair tables (RQ3/RQ4/RQ5).

Reuses already-validated machinery rather than recomputing from scratch:
  - results/offline_v2/canonical_runs.jsonl (strict-offline B0/B3/S1_S2_S3
    aggregate RiskyAcc/AFSP/DIR per model for RQ3/RQ4)
  - results/ablation_stats.json       (b3_baseline + per-stage B3_no_SN deltas)
  - pipeline.stats_paired              (_mcnemar_exact / _cohen_h / _odds_ratio_ci)
  - results/G_R2_REPAIR/table_*.csv    (RQ5 repair — already finalized in PR-07)

RQ3  controlled benchmark — paired intervention effect (B0 vs B3) + minimal gate.
RQ4  ablation — which stages drive the effect; minimal S1+S2+S3 gate vs full B3.
RQ5  repair — R0/R1/R2 functional/safety tradeoff (read-through from G_R2_REPAIR).
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

from pipeline.stats_paired import _mcnemar_exact, _cohen_h, _odds_ratio_ci

RESULTS = Path("results")
CANONICAL_RUNS = RESULTS / "offline_v2" / "canonical_runs.jsonl"
ABLATION_STATS = RESULTS / "ablation_stats.json"
G_R2_DIR = RESULTS / "G_R2_REPAIR"

MODEL_ORDER = ["Qwen-7B", "Qwen-14B", "Qwen-32B", "DeepSeek-6.7B", "CodeLlama-7B"]
MODEL_ID_TO_DISPLAY = {
    "Qwen2.5-Coder-7B-Instruct": "Qwen-7B",
    "Qwen2.5-Coder-14B-Instruct-AWQ": "Qwen-14B",
    "Qwen2.5-Coder-32B-Instruct-AWQ": "Qwen-32B",
    "deepseek-coder-6.7b-instruct": "DeepSeek-6.7B",
    "CodeLlama-7b-Instruct-hf": "CodeLlama-7B",
}


def _runs_by_model() -> dict:
    """Display model -> strict-offline canonical run dicts."""
    by = defaultdict(list)
    for line in CANONICAL_RUNS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        disp = MODEL_ID_TO_DISPLAY.get(r.get("model_id", "").split("/")[-1])
        if disp:
            by[disp].append(r)
    return by


def _rate(run, mode, *path):
    """Per-run strict-offline metric; None if unavailable."""
    cur = run.get("metrics_by_mode", {}).get(mode)
    for p in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur


def _mode_rate(runs, mode, *path):
    """Aggregate a canonical boolean metric for one model/mode."""
    n = len(runs)
    if not n:
        return None
    return sum(_rate(r, mode, *path) is True for r in runs) / n


def _strict_rq3_metrics(runs):
    """RQ3 source cells derived only from strict-offline canonical runs."""
    return {
        "n": len(runs),
        "RiskyAcc_B0": _mode_rate(runs, "B0", "accepted", "risky_accepted_patch"),
        "RiskyAcc_B3": _mode_rate(runs, "B3", "accepted", "risky_accepted_patch"),
        "RiskyAcc_S1S2S3": _mode_rate(
            runs, "S1_S2_S3", "accepted", "risky_accepted_patch"
        ),
        "FuncSucc": _mode_rate(runs, "B3", "generated", "functional_success"),
        "AFSP": _mode_rate(
            runs, "B3", "accepted", "risk_adjusted_success_core"
        ),
        "DIR_B3": _mode_rate(runs, "B3", "guard_metrics", "false_block"),
    }


def _paired(runs, left_mode, right_mode, metric_path):
    """Paired b/c counts + McNemar p + Cohen h + Haldane OR for two gate modes."""
    b = c = both1 = both0 = 0
    for r in runs:
        lv = _rate(r, left_mode, *metric_path)
        rv = _rate(r, right_mode, *metric_path)
        if lv is None or rv is None:
            continue
        if lv and rv:
            both1 += 1
        elif lv and not rv:
            b += 1
        elif rv and not lv:
            c += 1
        else:
            both0 += 1
    n = b + c + both1 + both0
    lr = (b + both1) / n if n else None
    rr = (c + both1) / n if n else None
    return {
        "n_pairs": n,
        f"{left_mode}_rate": round(lr, 4) if lr is not None else None,
        f"{right_mode}_rate": round(rr, 4) if rr is not None else None,
        f"{left_mode}_only": b, f"{right_mode}_only": c,
        "both": both1, "neither": both0,
        "mcnemar_p": round(_mcnemar_exact(b, c), 6),
        "cohen_h": round(_cohen_h(lr, rr), 4) if (lr is not None and rr is not None) else None,
        **{k: v for k, v in _odds_ratio_ci(both1, b, c, both0).items()},
    }


# --------------------------------------------------------------------------- #
# RQ3 — controlled benchmark gate effect
# --------------------------------------------------------------------------- #
def build_rq3() -> list[dict]:
    runs_by_model = _runs_by_model()
    rows = []
    for model in MODEL_ORDER:
        runs = runs_by_model.get(model, [])
        strict = _strict_rq3_metrics(runs)
        # Paired B0 vs B3 intervention effect on accepted risky patches.
        pair = _paired(runs, "B0", "B3", ("accepted", "risky_accepted_patch"))
        rows.append({
            "model": model,
            "n": strict["n"],
            "RiskyAcc_B0": round(strict["RiskyAcc_B0"], 4) if strict["RiskyAcc_B0"] is not None else "",
            "RiskyAcc_B3": round(strict["RiskyAcc_B3"], 4) if strict["RiskyAcc_B3"] is not None else "",
            "RiskyAcc_S1S2S3": round(strict["RiskyAcc_S1S2S3"], 4) if strict["RiskyAcc_S1S2S3"] is not None else "",
            "FuncSucc": round(strict["FuncSucc"], 4) if strict["FuncSucc"] is not None else "",
            "AFSP": round(strict["AFSP"], 4) if strict["AFSP"] is not None else "",
            "DIR_B3": round(strict["DIR_B3"], 4) if strict["DIR_B3"] is not None else "",
            "McNemar_p_B0_vs_B3": pair["mcnemar_p"],
            "cohen_h_B0_vs_B3": pair["cohen_h"],
            "odds_ratio_haldane_B0_vs_B3": pair.get("odds_ratio")
            or pair.get("or") or pair.get("odds_ratio_haldane", ""),
        })
    return rows


# --------------------------------------------------------------------------- #
# RQ4 — ablation: per-stage drivers + minimal S1+S2+S3 gate vs full B3
# --------------------------------------------------------------------------- #
def build_rq4() -> list[dict]:
    runs_by_model = _runs_by_model()
    with open(ABLATION_STATS) as f:
        ablation = json.load(f)
    b3_base = ablation.get("b3_baseline", {})
    abl = ablation.get("ablation", {})

    def _overall_risky(fam_cell):
        """RiskyAcc rate from a family-keyed cell dict (prefer 'Overall', else sum)."""
        if not isinstance(fam_cell, dict):
            return None
        ov = fam_cell.get("Overall")
        if isinstance(ov, dict) and ov.get("n"):
            return ov["k_risky"] / ov["n"]
        kr = sum(v.get("k_risky", 0) for k, v in fam_cell.items()
                 if k != "Overall" and isinstance(v, dict))
        n = sum(v.get("n", 0) for k, v in fam_cell.items()
                if k != "Overall" and isinstance(v, dict))
        return (kr / n) if n else None

    def _b3_overall_risky(model):
        return _overall_risky(b3_base.get(model, {}))

    def _ablation_delta(model, drop_mode):
        """ΔRiskyAcc (pp) when a stage is removed from B3 (B3_no_SN - B3)."""
        base = _b3_overall_risky(model)
        rate = _overall_risky(abl.get(model, {}).get(drop_mode))
        if base is None or rate is None:
            return None
        return round((rate - base) * 100, 1)

    rows = []
    for model in MODEL_ORDER:
        runs = runs_by_model.get(model, [])
        b3_risky = _mode_rate(runs, "B3", "accepted", "risky_accepted_patch")
        s123_risky = _mode_rate(runs, "S1_S2_S3", "accepted", "risky_accepted_patch")
        # Paired minimal-gate vs full-gate on accepted risky patches.
        pair = _paired(runs, "S1_S2_S3", "B3", ("accepted", "risky_accepted_patch"))
        rows.append({
            "model": model,
            "n": len(runs),
            "RiskyAcc_B3_full": round(b3_risky, 4) if b3_risky is not None else "",
            "RiskyAcc_S1S2S3_minimal": round(s123_risky, 4) if s123_risky is not None else "",
            "delta_minimal_minus_full_pp":
                round((s123_risky - b3_risky) * 100, 1)
                if s123_risky is not None and b3_risky is not None else "",
            "McNemar_p_S1S2S3_vs_B3": pair["mcnemar_p"],
            "cohen_h_S1S2S3_vs_B3": pair["cohen_h"],
            "ablation_delta_no_S1_pp": _ablation_delta(model, "B3_no_S1"),
            "ablation_delta_no_S2_pp": _ablation_delta(model, "B3_no_S2"),
            "ablation_delta_no_S3_pp": _ablation_delta(model, "B3_no_S3"),
            "ablation_delta_no_S4_pp": _ablation_delta(model, "B3_no_S4"),
            "ablation_delta_no_S5_pp": _ablation_delta(model, "B3_no_S5"),
            "ablation_delta_no_S6_pp": _ablation_delta(model, "B3_no_S6"),
        })
    return rows


# --------------------------------------------------------------------------- #
# RQ5 — repair tradeoff (read-through from the finalized G_R2_REPAIR tables)
# --------------------------------------------------------------------------- #
def build_rq5() -> list[dict]:
    """Merge G_R2_REPAIR all-run Table A (R0/R1/R2 FuncSucc/RiskyAcc/AFSP) with the
    blocked-subset repair outcomes and the McNemar verdicts into one RQ5 table."""
    ta = {}
    with open(G_R2_DIR / "table_A_all_runs.csv") as f:
        for row in csv.DictReader(f):
            ta[(row["Model"], row["Mode"])] = row
    mc = defaultdict(dict)
    with open(G_R2_DIR / "mcnemar_r1_vs_r2.csv") as f:
        for row in csv.DictReader(f):
            mc[row["Model"]][row["Metric"]] = row

    rows = []
    g_models = ["Qwen-7B", "Qwen-14B", "Qwen-32B", "DeepSeek-6.7B", "CodeLlama-7B"]
    for model in g_models:
        r0, r1, r2 = ta.get((model, "R0")), ta.get((model, "R1")), ta.get((model, "R2"))
        if not (r0 and r1 and r2):
            continue
        afsp_mc = mc[model].get("AFSP", {})
        func_mc = mc[model].get("FuncSucc", {})
        rows.append({
            "model": model,
            "n": r2.get("n", ""),
            "FuncSucc_R0": r0["FuncSucc"], "FuncSucc_R1": r1["FuncSucc"], "FuncSucc_R2": r2["FuncSucc"],
            "AFSP_R0_pre_strict": r0["AFSP_pre_strict"],
            "AFSP_R1_pre_strict": r1["AFSP_pre_strict"],
            "AFSP_R2_pre_strict": r2["AFSP_pre_strict"],
            "RiskyAcc_R0": r0["RiskyAcc"], "RiskyAcc_R1": r1["RiskyAcc"], "RiskyAcc_R2": r2["RiskyAcc"],
            "RepairAttemptRate_R2": r2.get("RepairAttemptRate", ""),
            "McNemar_p_FuncSucc_R1_vs_R2": func_mc.get("McNemar_p", ""),
            "McNemar_p_AFSP_R1_vs_R2": afsp_mc.get("McNemar_p", ""),
            "AFSP_favors": afsp_mc.get("favors", ""),
            "primary_case": afsp_mc.get("primary_case", ""),
        })
    return rows


if __name__ == "__main__":
    import sys
    for name, fn in (("RQ3", build_rq3), ("RQ4", build_rq4), ("RQ5", build_rq5)):
        rows = fn()
        print(f"=== {name} ({len(rows)} rows) ===")
        for r in rows:
            print(json.dumps(r, default=str))
        print()

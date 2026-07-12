"""
Artifact F: Recompute all paper tables and verify statistical consistency.

NOTE ON TABLE NUMBERING: the manuscript was reorganized into four RQs (RQ1 risk
surface, RQ2 gate effectiveness, RQ3 minimal effective checks, RQ4 external
validity) with safety-prompting and repair demoted to secondary analyses. The
PAPER_VALUES dict keys below (``tab2``/``tab3``/``tab4``) are HISTORICAL internal
labels, not the current printed table numbers; the recompute is model-keyed and
independent of table order. Current manuscript mapping:
  - tab2  -> Table 2 (RQ1, B0 risk per family/model)              [unchanged]
  - tab3  -> Table 9 (secondary analysis, G0 vs G1 safety prompt) [was Table 3]
  - tab4  -> Table 3 (RQ2, B0->B3 gate operating metrics)         [was Table 4]
  - ablation deltas -> Table 5 (RQ3, leave-one-out)               [was Table 6]
  - baseline ladder -> Table 4 (RQ3)                              [was Table 5]

Checks:
  - Table 2 (RQ1): denominators, Wilson CI bounds
  - Table 9 (secondary, G0 vs G1): McNemar p-values, Δ values, SafetyPass-All rates
  - Table 3 (RQ2): BlockRate, AFSP, DIR values
  - baseline ladder / scanner: RiskyAcc, FalseBlk, FalseAllow
  - Table 5 (RQ3) ablation: all Δ values
  - Main text stats: OR range, p < 10^-10 claim, DeepSeek -6.7pp, etc.

Outputs:
  results/recomputed_tables/  (CSV per table)
  results/statistical_consistency_check.md
"""

import csv
import json
import math
import argparse
import sys
from collections import defaultdict
from pathlib import Path
from scipy.stats import binomtest

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.compute_tse_stats import (
    collect_runs, mode_val, wilson_ci, mcnemar_exact, safety_pass_all
)
from pipeline.stats_paired import collect as collect_paired, compare_modes

RESULTS_DIR  = Path("results")
OUT_DIR      = Path("results/recomputed_tables")
CONSISTENCY_MD = RESULTS_DIR / "statistical_consistency_check.md"
OUT_DIR.mkdir(exist_ok=True)

MODEL_DISPLAY = {
    "Qwen2.5-Coder-7B-Instruct":    "Qwen-7B",
    "Qwen2.5-Coder-14B-Instruct-AWQ": "Qwen-14B",
    "Qwen2.5-Coder-32B-Instruct-AWQ": "Qwen-32B",
    "deepseek-coder-6.7b-instruct": "DeepSeek-6.7B",
    "CodeLlama-7b-Instruct-hf":     "CodeLlama-7B",
}
MODEL_ORDER = ["Qwen-7B", "Qwen-14B", "Qwen-32B", "DeepSeek-6.7B", "CodeLlama-7B"]
FAMILY_ORDER = ["F1", "F2", "F3", "F4", "F5", "F6"]

# Values as printed in the manuscript AFTER the deterministic canonical-run
# selection (2026-05-30 rewrite). collect_runs now selects the canonical run.
PAPER_VALUES = {
    # Table 2: overall B0 risk
    ("tab2", "Qwen-7B",       "Overall", "rate"): 0.262,
    ("tab2", "Qwen-14B",      "Overall", "rate"): 0.300,
    ("tab2", "Qwen-32B",      "Overall", "rate"): 0.229,
    ("tab2", "DeepSeek-6.7B", "Overall", "rate"): 0.138,
    ("tab2", "CodeLlama-7B",  "Overall", "rate"): 0.333,
    # Table 3: McNemar p (G0 vs G1, SafetyPass-Core)
    ("tab3", "Qwen-7B",       "mcnemar_p"):  0.0034,
    ("tab3", "DeepSeek-6.7B", "mcnemar_p"):  0.0023,
    ("tab3", "Qwen-7B",       "delta_sp"):   9.2,
    ("tab3", "DeepSeek-6.7B", "delta_sp"): -10.8,
    # Table 4: B3 RiskyAcc (unchanged by selection)
    ("tab4", "Qwen-7B",       "B3", "risky_acc"): 0.017,
    ("tab4", "Qwen-14B",      "B3", "risky_acc"): 0.008,
    ("tab4", "Qwen-32B",      "B3", "risky_acc"): 0.021,
    ("tab4", "DeepSeek-6.7B", "B3", "risky_acc"): 0.004,
    ("tab4", "CodeLlama-7B",  "B3", "risky_acc"): 0.075,
}

# Main-text odds ratios (Haldane discordant-pair OR, canonical selection).
MANUSCRIPT_OR = {
    "Qwen-7B": 119, "Qwen-14B": 141, "Qwen-32B": 101,
    "DeepSeek-6.7B": 65, "CodeLlama-7B": 125,
}
# Main-text claim: B0-vs-B3 McNemar p < 1e-10 for all EXCEPT DeepSeek-6.7B
# (p = 4.7e-10, b=32, just above the threshold).
MANUSCRIPT_P_LT_1E10 = {m: True for m in MODEL_ORDER}
MANUSCRIPT_P_LT_1E10["DeepSeek-6.7B"] = False

# Manuscript ablation deltas (Table tab:ablation), in pp, canonical selection.
MANUSCRIPT_ABLATION = {
    # model: {"S2": deltaPP, "S4": deltaPP, "S6": deltaPP, "F6_residual_B3": pct(0-100)}
    # S2 (version-validity) is a co-primary stage: removing it raises RiskyAcc by
    # +4.6..+12.9pp (>= S1 for 4/5 models) and explains the B2->B3 gap.
    "Qwen-7B":       {"S2": 10.0, "S4": 0.0, "S6": 0.0, "F6_residual_B3": 0.0},
    "Qwen-14B":      {"S2": 12.9, "S4": 0.0, "S6": 0.0, "F6_residual_B3": 0.0},
    "Qwen-32B":      {"S2": 9.2,  "S4": 0.0, "S6": 0.0, "F6_residual_B3": 0.0},
    "DeepSeek-6.7B": {"S2": 4.6,  "S4": 0.4, "S6": 0.0, "F6_residual_B3": 0.0},  # S4 catches 1 F5 transitive case
    "CodeLlama-7B":  {"S2": 5.4,  "S4": 0.0, "S6": 0.0, "F6_residual_B3": 40.0},
}

TOLERANCE = 0.005      # 0.5pp tolerance for rates — paper rounds to 1 decimal place
PP_TOLERANCE = 0.5     # 0.5pp tolerance for ablation deltas
OR_REL_TOLERANCE = 0.15  # 15% relative tolerance for odds ratios


def _or_mcnemar(b: int, c: int) -> float:
    """Odds ratio for McNemar (b/c with Haldane-Anscombe correction)."""
    bb = b + 0.5 if (b == 0 or c == 0) else b
    cc = c + 0.5 if (b == 0 or c == 0) else c
    return bb / cc


def collect_all_runs(
    results_dir: Path = RESULTS_DIR,
    runs_jsonl: Path | None = None,
):
    runs_by_model = {}
    for slug, display in MODEL_DISPLAY.items():
        runs = collect_runs(results_dir, slug, runs_jsonl=runs_jsonl)
        if runs:
            runs_by_model[display] = runs
    return runs_by_model


def check_table2(runs_by_model):
    rows = []
    mismatches = []
    for model in MODEL_ORDER:
        if model not in runs_by_model:
            continue
        runs = runs_by_model[model]
        for fam in FAMILY_ORDER + ["Overall"]:
            if fam == "Overall":
                subset = runs
            else:
                subset = [r for r in runs if r["task_id"].split("_")[1] == fam]
            k = sum(1 for r in subset if mode_val(r,"B0","accepted","risky_accepted_patch"))
            n = len(subset)
            rate = k/n if n else None
            lo, hi = wilson_ci(k, n)
            rows.append({"model":model,"family":fam,"k":k,"n":n,"rate":round(rate,4) if rate else None,
                         "ci_lo":round(lo,4) if lo else None,"ci_hi":round(hi,4) if hi else None})
            paper_key = ("tab2", model, fam, "rate")
            if paper_key in PAPER_VALUES and rate is not None:
                diff = abs(rate - PAPER_VALUES[paper_key])
                if diff > TOLERANCE:
                    mismatches.append(f"Table2 {model} {fam}: paper={PAPER_VALUES[paper_key]:.3f} computed={rate:.3f} diff={diff:.3f}")
    return rows, mismatches


def check_table3(runs_by_model):
    rows = []
    mismatches = []
    for model in MODEL_ORDER:
        if model not in runs_by_model:
            continue
        runs = runs_by_model[model]
        for cond in ("G0","G1"):
            subset = [r for r in runs if r["generation_condition"] == cond]
            n = len(subset)
            if n == 0:
                continue
            fs   = sum(1 for r in subset if mode_val(r,"B3","generated","functional_success"))
            spc  = sum(1 for r in subset if mode_val(r,"B3","generated","safety_pass_core"))
            spa_vals = [safety_pass_all(r) for r in subset]
            spa = sum(1 for v in spa_vals if v is True)
            spa_n = sum(1 for v in spa_vals if v is not None)
            ra   = sum(1 for r in subset if mode_val(r,"B3","accepted","risky_accepted_patch"))
            rows.append({"model":model,"cond":cond,"n":n,
                         "func_succ":round(fs/n,4),"safety_core":round(spc/n,4),
                         "safety_all":round(spa/spa_n,4) if spa_n else None,
                         "risky_acc":round(ra/n,4)})
        # McNemar
        g0 = {r["task_id"]: r for r in runs if r["generation_condition"]=="G0"}
        g1 = {r["task_id"]: r for r in runs if r["generation_condition"]=="G1"}
        common = sorted(set(g0)&set(g1))
        b=c=0
        for tid in common:
            v0 = mode_val(g0[tid],"B3","generated","safety_pass_core")
            v1 = mode_val(g1[tid],"B3","generated","safety_pass_core")
            if v0 is None or v1 is None: continue
            if v0 and not v1: b+=1
            elif v1 and not v0: c+=1
        p = mcnemar_exact(b,c)
        g0_sp = sum(1 for r in runs if r["generation_condition"]=="G0" and mode_val(r,"B3","generated","safety_pass_core"))
        g1_sp = sum(1 for r in runs if r["generation_condition"]=="G1" and mode_val(r,"B3","generated","safety_pass_core"))
        g0_n  = sum(1 for r in runs if r["generation_condition"]=="G0")
        g1_n  = sum(1 for r in runs if r["generation_condition"]=="G1")
        delta_sp = (g1_sp/g1_n - g0_sp/g0_n)*100 if g0_n and g1_n else None
        rows.append({"model":model,"cond":"McNemar","n":len(common),
                     "p_value":round(p,4),"b":b,"c":c,"delta_sp":round(delta_sp,2) if delta_sp else None})
        # mcnemar_p compared with rate tolerance; delta_sp is in pp → use PP_TOLERANCE.
        for key, expected, tol in [(("tab3",model,"mcnemar_p"), p, TOLERANCE),
                                   (("tab3",model,"delta_sp"), delta_sp, PP_TOLERANCE)]:
            if key in PAPER_VALUES and expected is not None:
                diff = abs(expected - PAPER_VALUES[key])
                if diff > tol:
                    mismatches.append(f"Table3 {model} {key[-1]}: paper={PAPER_VALUES[key]:.3f} computed={expected:.3f}")
    return rows, mismatches


def check_table4(runs_by_model):
    rows = []
    mismatches = []
    for model in MODEL_ORDER:
        if model not in runs_by_model:
            continue
        runs = runs_by_model[model]
        n = len(runs)
        for mode in ("B0","B3","R1"):
            fs  = sum(1 for r in runs if mode_val(r,mode,"generated","functional_success"))
            spc = sum(1 for r in runs if mode_val(r,mode,"generated","safety_pass_core"))
            ra  = sum(1 for r in runs if mode_val(r,mode,"accepted","risky_accepted_patch"))
            fb  = sum(1 for r in runs if mode_val(r,mode,"guard_metrics","false_block"))
            fa  = sum(1 for r in runs if mode_val(r,mode,"guard_metrics","false_allow"))
            pa  = [mode_val(r,mode,"accepted","patch_accepted") for r in runs]
            blocked = sum(1 for v in pa if v is False)
            afsp = sum(1 for r in runs if
                       mode_val(r,mode,"accepted","patch_accepted") is True
                       and mode_val(r,mode,"accepted","functional_success") is True
                       and mode_val(r,mode,"accepted","safety_pass_core") is True)
            block_rate = blocked/n if n else None
            rows.append({"model":model,"mode":mode,"n":n,
                         "func_succ":round(fs/n,4),"safety_core":round(spc/n,4),
                         "risky_acc":round(ra/n,4),"false_block":round(fb/n,4),
                         "false_allow":round(fa/n,4),
                         "block_rate":round(block_rate,4) if block_rate is not None else None,
                         "afsp":round(afsp/n,4),"dir":round(fb/n,4)})
            key = ("tab4",model,mode,"risky_acc")
            if key in PAPER_VALUES:
                diff = abs(ra/n - PAPER_VALUES[key])
                if diff > TOLERANCE:
                    mismatches.append(f"Table4 {model} {mode} RiskyAcc: paper={PAPER_VALUES[key]:.3f} computed={ra/n:.3f}")
        # B0→B3 odds ratio
        b0_risky = sum(1 for r in runs if mode_val(r,"B0","accepted","risky_accepted_patch"))
        b3_risky = sum(1 for r in runs if mode_val(r,"B3","accepted","risky_accepted_patch"))
        # Paired McNemar for B0 vs B3
        b=c=0
        for r in runs:
            v0 = mode_val(r,"B0","accepted","risky_accepted_patch")
            v3 = mode_val(r,"B3","accepted","risky_accepted_patch")
            if v0 and not v3: b+=1
            elif v3 and not v0: c+=1
        p_b0b3 = mcnemar_exact(b,c)
        # Crude OR
        p0 = b0_risky/n if n else 0
        p3 = b3_risky/n if n else 0
        or_val = (p0/(1-p0+1e-9)) / (p3/(1-p3+1e-9)) if p3 > 0 else float("inf")
        # Keep p UNROUNDED (rounding to 6 d.p. collapses ~1e-7 to 0.0).
        rows.append({"model":model,"mode":"B0vsB3_McNemar","n":n,
                     "p_value":p_b0b3,"odds_ratio":round(or_val,1)})
    return rows, mismatches


def check_parser_contamination(runs_by_model: dict[str, list[dict]] | None = None):
    """Scan deduplicated benchmark runs for source-token 'packages' produced by
    the (pre-fix) dependency parser, e.g. 'import', 'def', 'return'. These are
    measurement artifacts: the stored result.json dep_changes were never
    regenerated after the parser fix covered by tests/test_dependency_parser.py."""
    SUSPECT = {
        "import","from","class","def","try","except","with","pass","return","if",
        "else","elif","for","while","in","and","or","not","is","none","true","false",
        "self","print","raise","yield","lambda","assert","del","global","async","await",
        "break","continue",
    }
    if runs_by_model is None:
        from pipeline.config import is_canonical_run
        by = {}
        for p in RESULTS_DIR.glob("task_*/*/result.json"):
            if not is_canonical_run(p.parent.name):   # deterministic: canonical run only
                continue
            try:
                r = json.loads(p.read_text())
            except Exception:
                continue
            slug = r.get("model_id","").rsplit("/",1)[-1]
            if slug not in MODEL_DISPLAY or "metrics_by_mode" not in r:
                continue
            key = (r["task_id"], r["generation_condition"], slug)
            mt = p.stat().st_mtime
            if key not in by or mt > by[key][0]:
                by[key] = (mt, r)
        records = [
            (task, cond, MODEL_DISPLAY[slug], r)
            for (task, cond, slug), (mt, r) in sorted(by.items())
        ]
    else:
        records = [
            (r.get("task_id"), r.get("generation_condition"), model, r)
            for model, runs in runs_by_model.items()
            for r in runs
        ]

    rows = []
    for task, cond, model, r in records:
        toks = [d.get("package") for d in (r.get("dep_changes") or [])
                if str(d.get("package","")).lower() in SUSPECT]
        if not toks:
            continue
        adds = [d.get("package") for d in (r.get("dep_changes") or [])
                if d.get("change_type") == "added"]
        real = [a for a in adds if str(a).lower() not in SUSPECT]
        rows.append({
            "task_id": task, "cond": cond, "model": model,
            "token_pkgs": ",".join(map(str, toks)),
            "real_added_pkgs": ",".join(map(str, real)) or "(none)",
            "b0_risky": mode_val(r,"B0","accepted","risky_accepted_patch"),
            "b3_risky": mode_val(r,"B3","accepted","risky_accepted_patch"),
            "pure_artifact": len(real) == 0,
        })

    mismatches = []
    if rows:
        n_pure_b3 = sum(1 for x in rows if x["pure_artifact"] and x["b3_risky"])
        mismatches.append(
            f"ParserArtifact: {len(rows)} deduplicated benchmark run(s) contain source-token "
            f"'packages' (parser FP); {n_pure_b3} are pure-artifact AND risky at B3 "
            f"(inflate residual risk). See parser_contamination.csv. Regenerate dep_changes "
            f"with the fixed parser before final numbers.")
    return rows, mismatches


def check_main_text_claims(runs_by_model):
    """Recompute B0-vs-B3 odds ratios (two definitions) and exact McNemar p.

    NOTE: p is kept UNROUNDED for the < 1e-10 comparison. A prior version
    rounded p to 6 d.p., which collapsed DeepSeek's 2.4e-7 to 0.0 and made
    the < 1e-10 test spuriously pass. Do not round before comparing.
    """
    claims = []
    mismatches = []
    for model in MODEL_ORDER:
        if model not in runs_by_model:
            continue
        runs = runs_by_model[model]
        n = len(runs)
        b0 = sum(1 for r in runs if mode_val(r,"B0","accepted","risky_accepted_patch"))
        b3 = sum(1 for r in runs if mode_val(r,"B3","accepted","risky_accepted_patch"))
        b=c=0
        for r in runs:
            v0 = mode_val(r,"B0","accepted","risky_accepted_patch")
            v3 = mode_val(r,"B3","accepted","risky_accepted_patch")
            if v0 and not v3: b+=1
            elif v3 and not v0: c+=1
        p = mcnemar_exact(b,c)               # UNROUNDED
        p0 = b0/n; p3 = b3/n
        or_crude  = (p0/(1-p0+1e-9))/(p3/(1-p3+1e-9)) if p3>0 else float("inf")
        or_paired = _or_mcnemar(b, c)        # Haldane-corrected b/c (undefined when c=0)
        p_lt = p < 1e-10
        claims.append({
            "model": model,
            "b0_risky_rate": round(p0,4),
            "b3_risky_rate": round(p3,4),
            "mcnemar_b": b, "mcnemar_c": c,
            "p_b0_vs_b3": f"{p:.3e}",
            "p_lt_1e10": p_lt,
            "odds_ratio_crude": round(or_crude,1),
            "odds_ratio_paired_haldane": round(or_paired,1),
            "manuscript_or": MANUSCRIPT_OR.get(model),
        })

        # --- cross-check against manuscript ---
        # (1) p < 1e-10 claim
        if MANUSCRIPT_P_LT_1E10.get(model) and not p_lt:
            mismatches.append(
                f"MainText {model}: manuscript claims p<1e-10 but exact McNemar "
                f"p={p:.2e} (b={b}, c={c}) — claim FALSE for this model")
        # (2) odds ratio — flag if BOTH definitions miss the manuscript value
        mor = MANUSCRIPT_OR.get(model)
        if mor is not None:
            def rel_off(x):
                return abs(x - mor) / mor if x not in (float("inf"),) else 1.0
            if rel_off(or_crude) > OR_REL_TOLERANCE and rel_off(or_paired) > OR_REL_TOLERANCE:
                mismatches.append(
                    f"MainText {model}: manuscript OR={mor} not reproduced by crude "
                    f"OR={or_crude:.1f} nor Haldane paired OR={or_paired:.1f} "
                    f"(c={c}; paired OR undefined when c=0)")
    return claims, mismatches


ABLATION_MODE_BY_STAGE = {
    "S2": "B3_no_S2",
    "S4": "B3_no_S4",
    "S6": "B3_no_S6",
}


def _required_risky_value(row: dict, model: str, mode: str, row_index: int) -> bool:
    risky = mode_val(row, mode, "accepted", "risky_accepted_patch")
    if not isinstance(risky, bool):
        task = row.get("task_id", "<unknown-task>")
        cond = row.get("generation_condition", "<unknown-cond>")
        raise ValueError(
            f"Ablation {model}: row {row_index} ({task}/{cond}) missing or invalid "
            f"{mode}.accepted.risky_accepted_patch"
        )
    return risky


def _collect_ablation_from_runs(runs_by_model: dict[str, list[dict]]):
    b3 = defaultdict(lambda: [0, 0])
    b3_f6 = defaultdict(lambda: [0, 0])
    abl = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    required_modes = ("B3", *ABLATION_MODE_BY_STAGE.values())

    for model, runs in runs_by_model.items():
        for row_index, row in enumerate(runs, start=1):
            values = {
                mode: _required_risky_value(row, model, mode, row_index)
                for mode in required_modes
            }
            b3[model][1] += 1
            b3[model][0] += 1 if values["B3"] else 0
            if row["task_id"].split("_")[1] == "F6":
                b3_f6[model][1] += 1
                b3_f6[model][0] += 1 if values["B3"] else 0
            for mode in ABLATION_MODE_BY_STAGE.values():
                abl[model][mode][1] += 1
                abl[model][mode][0] += 1 if values[mode] else 0

    return b3, b3_f6, abl


def check_ablation(runs_by_model: dict[str, list[dict]] | None = None):
    """Recompute S2/S4/S6 ablation deltas and CodeLlama F6 residual.

    With strict-offline canonical runs, ablated modes are taken directly from
    metrics_by_mode. The legacy ablation_raw.jsonl fallback is used only for
    callers that do not supply runs_by_model.
    """
    rows = []
    mismatches = []

    if runs_by_model is not None:
        b3, b3_f6, abl = _collect_ablation_from_runs(runs_by_model)
    else:
        abl_path = RESULTS_DIR / "ablation_raw.jsonl"
        if not abl_path.exists():
            return rows, ["Ablation: results/ablation_raw.jsonl missing — cannot verify ablation deltas"]

        # stored B3 (overall + F6) per model, deduplicated by (task, cond)
        b3 = defaultdict(lambda: [0, 0])      # model -> [risky, n]
        b3_f6 = defaultdict(lambda: [0, 0])
        runs_by_model = collect_all_runs()
        for model, runs in runs_by_model.items():
            for r in runs:
                risky = mode_val(r, "B3", "accepted", "risky_accepted_patch")
                b3[model][1] += 1; b3[model][0] += 1 if risky else 0
                if r["task_id"].split("_")[1] == "F6":
                    b3_f6[model][1] += 1; b3_f6[model][0] += 1 if risky else 0

        # ablated modes from raw jsonl
        abl = defaultdict(lambda: defaultdict(lambda: [0, 0]))
        for line in abl_path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            m = row["model"]
            for mode, d in row.get("ablation", {}).items():
                risky = d["metrics"]["accepted"]["risky_accepted_patch"]
                abl[m][mode][1] += 1; abl[m][mode][0] += 1 if risky else 0

    for model in MODEL_ORDER:
        if b3[model][1] == 0:
            continue
        base = 100 * b3[model][0] / b3[model][1]
        for mode in ABLATION_MODE_BY_STAGE.values():
            if abl[model][mode][1] == 0:
                raise ValueError(f"Ablation {model}: no {mode} rows available")
        d2 = (
            100 * abl[model][ABLATION_MODE_BY_STAGE["S2"]][0]
            / abl[model][ABLATION_MODE_BY_STAGE["S2"]][1]
            - base
        )
        d4 = (
            100 * abl[model][ABLATION_MODE_BY_STAGE["S4"]][0]
            / abl[model][ABLATION_MODE_BY_STAGE["S4"]][1]
            - base
        )
        d6 = (
            100 * abl[model][ABLATION_MODE_BY_STAGE["S6"]][0]
            / abl[model][ABLATION_MODE_BY_STAGE["S6"]][1]
            - base
        )
        f6res = 100 * b3_f6[model][0] / b3_f6[model][1] if b3_f6[model][1] else 0.0
        rows.append({"model": model, "b3_overall": round(base, 1),
                     "delta_S2": round(d2, 1),
                     "delta_S4": round(d4, 1), "delta_S6": round(d6, 1),
                     "f6_residual_b3": round(f6res, 1)})
        exp = MANUSCRIPT_ABLATION.get(model, {})
        if "S2" in exp and abs(d2 - exp["S2"]) > PP_TOLERANCE:
            mismatches.append(f"Ablation {model} ΔS2: paper={exp['S2']:+.1f}pp computed={d2:+.1f}pp")
        if "S4" in exp and abs(d4 - exp["S4"]) > PP_TOLERANCE:
            mismatches.append(f"Ablation {model} ΔS4: paper={exp['S4']:+.1f}pp computed={d4:+.1f}pp")
        if "S6" in exp and abs(d6 - exp["S6"]) > PP_TOLERANCE:
            mismatches.append(f"Ablation {model} ΔS6: paper={exp['S6']:+.1f}pp computed={d6:+.1f}pp")
        if "F6_residual_B3" in exp and abs(f6res - exp["F6_residual_B3"]) > 1.0:
            mismatches.append(f"Ablation {model} F6 residual: paper={exp['F6_residual_B3']:.0f}% computed={f6res:.1f}%")

    # Prose-vs-table contradiction inside the manuscript itself.
    cl = next((r for r in rows if r["model"] == "CodeLlama-7B"), None)
    if cl is not None and abs(cl["delta_S4"]) > PP_TOLERANCE:
        mismatches.append(
            f"Manuscript PROSE (results.tex:389) states 'S4 Δ=0.0pp for all models', "
            f"but the ablation TABLE (results.tex:363) and recomputation give "
            f"CodeLlama ΔS4={cl['delta_S4']:+}pp — prose overstates the all-models claim.")
    return rows, mismatches


def write_csv(rows, path):
    if not rows:
        return
    # Collect all fieldnames across all rows (rows may have different keys)
    all_keys = list(dict.fromkeys(k for r in rows for k in r.keys()))
    with open(path,"w",newline="") as f:
        w = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for row in rows:
            padded = {k: row.get(k,"") for k in all_keys}
            w.writerow(padded)


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    ap.add_argument("--runs-jsonl", type=Path, default=None)
    return ap


def main(argv: list[str] | None = None):
    args = build_arg_parser().parse_args(argv)

    print("Collecting runs...")
    runs_by_model = collect_all_runs(
        results_dir=args.results_dir,
        runs_jsonl=args.runs_jsonl,
    )
    for m, runs in runs_by_model.items():
        print(f"  {m}: {len(runs)} runs")

    # Integrity guard: with no per-run data every check skips its models and
    # reports a vacuous "all consistent" — a false positive. The per-run
    # result.json under results/task_*/ is gitignored (see .gitignore) and ships
    # only in the artifact ZIP, so a bare git clone lands here with 0 runs. Fail
    # loudly instead of green-lighting zero checks.
    total_runs = sum(len(r) for r in runs_by_model.values())
    if total_runs == 0:
        source = (
            f"{args.runs_jsonl}"
            if args.runs_jsonl
            else f"{args.results_dir}/task_*/"
        )
        print(
            f"\nERROR: collected 0 per-run results from {source}.\n"
            "  These files are gitignored and are NOT in a bare git clone.\n"
            "  Run this from the unpacked artifact ZIP or a populated working\n"
            "  tree, not a fresh clone. Refusing to report a vacuous PASS.",
            file=sys.stderr,
        )
        sys.exit(2)

    print("\nChecking Table 2...")
    t2_rows, t2_mis = check_table2(runs_by_model)
    write_csv(t2_rows, OUT_DIR/"table2_recomputed.csv")

    print("Checking Table 3...")
    t3_rows, t3_mis = check_table3(runs_by_model)
    write_csv(t3_rows, OUT_DIR/"table3_recomputed.csv")

    print("Checking Table 4...")
    t4_rows, t4_mis = check_table4(runs_by_model)
    write_csv(t4_rows, OUT_DIR/"table4_recomputed.csv")

    print("Checking main text claims (OR, p < 10^-10)...")
    claims, mt_mis = check_main_text_claims(runs_by_model)
    write_csv(claims, OUT_DIR/"main_text_claims.csv")

    print("Checking ablation deltas (S2, S4, S6, F6 residual)...")
    ablation_runs = runs_by_model if args.runs_jsonl is not None else None
    abl_rows, abl_mis = check_ablation(ablation_runs)
    write_csv(abl_rows, OUT_DIR/"ablation_recomputed.csv")

    print("Scanning for parser-artifact dependencies in benchmark runs...")
    parser_rows, parser_mis = check_parser_contamination(runs_by_model)
    write_csv(parser_rows, OUT_DIR/"parser_contamination.csv")

    all_mismatches = t2_mis + t3_mis + t4_mis + mt_mis + abl_mis + parser_mis

    # Report
    md = ["# Artifact F: Statistical Consistency Check\n"]
    md.append("Tolerance: rates ±0.5 pp; ablation deltas ±0.5 pp; odds ratios ±15% (relative).\n")
    if not all_mismatches:
        md.append("**All checked values match the manuscript within tolerance.**\n")
    else:
        md.append(f"**{len(all_mismatches)} mismatch(es)/flag(s) found:**\n")
        for m in all_mismatches:
            md.append(f"- {m}")
        md.append("")

    md += ["\n## Table 2 — Overall B0 risk rates\n",
           "| Model | k | n | Rate | [95% CI] |",
           "|-------|---|---|------|----------|"]
    for r in t2_rows:
        if r["family"] == "Overall":
            ci = f"[{100*r['ci_lo']:.0f}–{100*r['ci_hi']:.0f}]" if r["ci_lo"] else "—"
            md.append(f"| {r['model']} | {r['k']} | {r['n']} | {100*r['rate']:.1f}% | {ci} |")

    md += ["\n## Table 3 — McNemar p-values (G0 vs G1, SafetyPass-Core)\n",
           "| Model | b | c | p-value | Δ SafetyPass (pp) |",
           "|-------|---|---|---------|-------------------|"]
    for r in t3_rows:
        if r.get("cond") == "McNemar":
            md.append(f"| {r['model']} | {r.get('b','?')} | {r.get('c','?')} | "
                      f"{r.get('p_value','?')} | {r.get('delta_sp','?')} |")

    md += ["\n## Table 4 / Main text — B0 vs B3 McNemar, odds ratio, p<10⁻¹⁰\n",
           "Manuscript OR is the printed value (results.tex:180-183). Crude = marginal OR; "
           "Paired = Haldane-corrected b/c (undefined when c=0). Exact McNemar p is UNROUNDED.\n",
           "| Model | b | c | OR crude | OR paired | OR manuscript | p (B0 vs B3) | p<10⁻¹⁰? |",
           "|-------|---|---|----------|-----------|---------------|--------------|----------|"]
    for r in claims:
        flag = "YES ✓" if r["p_lt_1e10"] else "**NO ✗**"
        md.append(f"| {r['model']} | {r['mcnemar_b']} | {r['mcnemar_c']} | "
                  f"{r['odds_ratio_crude']} | {r['odds_ratio_paired_haldane']} | "
                  f"{r['manuscript_or']} | {r['p_b0_vs_b3']} | {flag} |")

    md += ["\n## Ablation — recomputed S2/S4/S6 deltas and CodeLlama F6 residual\n",
           "| Model | B3 overall | ΔS2 (pp) | ΔS4 (pp) | ΔS6 (pp) | F6 residual @B3 |",
           "|-------|-----------|----------|----------|----------|-----------------|"]
    for r in abl_rows:
        md.append(f"| {r['model']} | {r['b3_overall']}% | {r['delta_S2']:+} | {r['delta_S4']:+} | "
                  f"{r['delta_S6']:+} | {r['f6_residual_b3']}% |")

    md += ["\n## Parser-artifact contamination (benchmark dep_changes)\n"]
    if parser_rows:
        md += ["| Task | Cond | Model | Token pkgs | Real added | B0 risky | B3 risky | Pure artifact |",
               "|------|------|-------|-----------|-----------|----------|----------|---------------|"]
        for r in parser_rows:
            md.append(f"| {r['task_id']} | {r['cond']} | {r['model']} | {r['token_pkgs']} | "
                      f"{r['real_added_pkgs']} | {r['b0_risky']} | {r['b3_risky']} | {r['pure_artifact']} |")
    else:
        md.append("None found.")

    md += ["\n## Recomputed table files\n",
           f"- `{OUT_DIR}/table2_recomputed.csv`",
           f"- `{OUT_DIR}/table3_recomputed.csv`",
           f"- `{OUT_DIR}/table4_recomputed.csv`",
           f"- `{OUT_DIR}/main_text_claims.csv`",
           f"- `{OUT_DIR}/ablation_recomputed.csv`",
           f"- `{OUT_DIR}/parser_contamination.csv`",
           ]

    CONSISTENCY_MD.write_text("\n".join(md))
    print(f"\nWrote {CONSISTENCY_MD}")
    if all_mismatches:
        print(f"\n⚠️  {len(all_mismatches)} mismatches:")
        for m in all_mismatches:
            print(f"  {m}")
        sys.exit(1)
    else:
        print("\n✓ All values consistent with manuscript.")


if __name__ == "__main__":
    main()

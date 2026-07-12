#!/usr/bin/env python3
"""Cross-seed variance analysis for AgentSupplyBench-Py.

GPU-free. Reads the on-disk per-run result.json files (canonical seed 0 +
_s1_/_s2_ replicates) and computes, per (model, condition, seed):
  - B0 RiskyAcc, B3 RiskyAcc (accepted-level), SafetyPass-Core (generated-level)
and per (model):
  - across-seed mean/SD of B0 and B3 RiskyAcc   (validates threats.tex "<=3.3pp / <=1.3pp")
  - per-task seed-disagreement rate at B0 and B3 (validates threats.tex "4-17% / 0-2%")
  - ΔSafetyPass-Core (G1-G0) computed separately per seed -> sign stability of the
    RQ2 grounding effect (the key robustness number for H2a/H2b).

All stats scripts in pipeline/ hard-filter to is_canonical_run() and skip the
seed replicates, so no committed script produced these numbers before. _mr3_
(repair ablation) dirs are excluded; they are not seeds.

Run:  python pipeline/compute_seed_variance.py
Out:  results/seed_variance.json , results/seed_variance.md
"""
import json
import os
import re
import statistics
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(ROOT, "results")

# Friendly model names keyed by the run-dir slug prefix.
MODEL_NAMES = {
    "Qwen2.5-Coder-7B-Instruct": "Qwen-7B",
    "Qwen2.5-Coder-14B-Instruct-AWQ": "Qwen-14B",
    "Qwen2.5-Coder-32B-Instruct-AWQ": "Qwen-32B",
    "deepseek-coder-6.7b-instruct": "DeepSeek-6.7B",
    "CodeLlama-7b-Instruct-hf": "CodeLlama-7B",
}
ORDER = ["Qwen-7B", "Qwen-14B", "Qwen-32B", "DeepSeek-6.7B", "CodeLlama-7B"]

DIR_RE = re.compile(r"^(?P<model>.+)_(?P<cond>G[01])_(?P<suffix>.+)$")


def parse_rundir(name):
    """Return (model_slug, cond, seed) or None to skip (_mr3_ or unparseable)."""
    m = DIR_RE.match(name)
    if not m:
        return None
    suffix = m.group("suffix")
    if suffix.startswith("mr3_"):
        return None  # repair ablation, not a seed
    if suffix.startswith("s1_"):
        seed = 1
    elif suffix.startswith("s2_"):
        seed = 2
    elif re.fullmatch(r"[0-9a-fA-F]+", suffix):
        seed = 0  # canonical
    else:
        return None
    return m.group("model"), m.group("cond"), seed


def collect():
    """{(model_name, cond, seed): {task_id: {'b0':bool,'b3':bool,'spc':bool}}}"""
    cells = defaultdict(dict)            # key -> task_id -> metrics
    mtimes = defaultdict(dict)           # key -> task_id -> mtime (for dedup)
    skipped = defaultdict(int)
    for task_entry in os.scandir(RESULTS):
        if not (task_entry.is_dir() and task_entry.name.startswith("task_")):
            continue
        for run in os.scandir(task_entry.path):
            if not run.is_dir():
                continue
            parsed = parse_rundir(run.name)
            if parsed is None:
                continue
            slug, cond, seed = parsed
            model = MODEL_NAMES.get(slug)
            if model is None:
                skipped["unknown_model"] += 1
                continue
            rj = os.path.join(run.path, "result.json")
            if not os.path.exists(rj):
                continue
            try:
                d = json.load(open(rj))
            except Exception:
                skipped["bad_json"] += 1
                continue
            tid = d.get("task_id") or task_entry.name
            mbm = d.get("metrics_by_mode", {})
            try:
                b0 = bool(mbm["B0"]["accepted"]["risky_accepted_patch"])
                b3 = bool(mbm["B3"]["accepted"]["risky_accepted_patch"])
                spc = bool(mbm["B3"]["generated"]["safety_pass_core"])
            except (KeyError, TypeError):
                skipped["missing_metric"] += 1
                continue
            key = (model, cond, seed)
            mt = os.path.getmtime(rj)
            if tid in mtimes[key] and mt <= mtimes[key][tid]:
                continue  # keep the latest run for a (model,cond,seed,task) on retry dups
            mtimes[key][tid] = mt
            cells[key][tid] = {"b0": b0, "b3": b3, "spc": spc}
    return cells, dict(skipped)


def rate(vals):
    return 100.0 * sum(vals) / len(vals) if vals else float("nan")


def main():
    cells, skipped = collect()

    # Per-cell summary
    cell_summary = {}
    for (model, cond, seed), tasks in cells.items():
        b0 = [v["b0"] for v in tasks.values()]
        b3 = [v["b3"] for v in tasks.values()]
        spc = [v["spc"] for v in tasks.values()]
        cell_summary[f"{model}|{cond}|s{seed}"] = {
            "n_tasks": len(tasks),
            "B0_RiskyAcc": round(rate(b0), 1),
            "B3_RiskyAcc": round(rate(b3), 1),
            "SafetyPassCore": round(rate(spc), 1),
        }

    per_model = {}
    for model in ORDER:
        seeds = sorted({s for (m, c, s) in cells if m == model})
        if not seeds:
            continue
        # across-seed SD of full-benchmark (G0+G1 pooled) B0/B3 RiskyAcc
        b0_by_seed, b3_by_seed = [], []
        for s in seeds:
            pooled_b0, pooled_b3 = [], []
            for cond in ("G0", "G1"):
                t = cells.get((model, cond, s), {})
                pooled_b0 += [v["b0"] for v in t.values()]
                pooled_b3 += [v["b3"] for v in t.values()]
            if pooled_b0:
                b0_by_seed.append(rate(pooled_b0))
                b3_by_seed.append(rate(pooled_b3))

        # ΔSafetyPass-Core (G1 - G0) per seed (paired by task within seed)
        dspc_by_seed = {}
        for s in seeds:
            g0 = cells.get((model, "G0", s), {})
            g1 = cells.get((model, "G1", s), {})
            common = set(g0) & set(g1)
            if common:
                spc_g0 = rate([g0[t]["spc"] for t in common])
                spc_g1 = rate([g1[t]["spc"] for t in common])
                dspc_by_seed[s] = round(spc_g1 - spc_g0, 1)

        # per-task seed-disagreement: among tasks present in >=2 seeds (per cond,
        # pooled), fraction whose risky outcome is not unanimous across seeds.
        def disagreement(metric):
            flips_total = 0
            tasks_total = 0
            for cond in ("G0", "G1"):
                seed_maps = [cells.get((model, cond, s), {}) for s in seeds]
                seed_maps = [m for m in seed_maps if m]
                if len(seed_maps) < 2:
                    continue
                common = set.intersection(*[set(m) for m in seed_maps])
                for t in common:
                    outcomes = {sm[t][metric] for sm in seed_maps}
                    tasks_total += 1
                    if len(outcomes) > 1:
                        flips_total += 1
            return round(100.0 * flips_total / tasks_total, 1) if tasks_total else None

        sd_b0 = round(statistics.pstdev(b0_by_seed), 1) if len(b0_by_seed) > 1 else 0.0
        sd_b3 = round(statistics.pstdev(b3_by_seed), 1) if len(b3_by_seed) > 1 else 0.0
        signs = {("+" if d > 0 else "-" if d < 0 else "0") for d in dspc_by_seed.values()}
        per_model[model] = {
            "n_seeds": len(seeds),
            "seeds": seeds,
            "B0_RiskyAcc_by_seed": [round(x, 1) for x in b0_by_seed],
            "B3_RiskyAcc_by_seed": [round(x, 1) for x in b3_by_seed],
            "B0_RiskyAcc_SD": sd_b0,
            "B3_RiskyAcc_SD": sd_b3,
            "deltaSafetyPassCore_by_seed": dspc_by_seed,
            "delta_sign_stable": (len(signs) == 1) if dspc_by_seed else None,
            "seed_disagreement_B0_pct": disagreement("b0"),
            "seed_disagreement_B3_pct": disagreement("b3"),
        }

    out = {
        "_note": "Cross-seed variance from on-disk replicates (canonical seed0 + _s1_/_s2_); _mr3_ excluded. GPU-free.",
        "skipped": skipped,
        "per_model": per_model,
        "per_cell": cell_summary,
    }
    os.makedirs(RESULTS, exist_ok=True)
    json.dump(out, open(os.path.join(RESULTS, "seed_variance.json"), "w"), indent=2)

    # Markdown table
    lines = ["# Seed-variance analysis (results/seed_variance.json)", "",
             "| Model | #seeds | B0 RiskyAcc by seed | SD | B3 by seed | SD | ΔSP-Core/seed (G1−G0) | sign-stable | disagree B0% | disagree B3% |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for model in ORDER:
        if model not in per_model:
            continue
        m = per_model[model]
        d = m["deltaSafetyPassCore_by_seed"]
        dstr = ", ".join(f"s{k}:{v:+}" for k, v in sorted(d.items()))
        lines.append(
            f"| {model} | {m['n_seeds']} | {m['B0_RiskyAcc_by_seed']} | {m['B0_RiskyAcc_SD']} | "
            f"{m['B3_RiskyAcc_by_seed']} | {m['B3_RiskyAcc_SD']} | {dstr} | "
            f"{m['delta_sign_stable']} | {m['seed_disagreement_B0_pct']} | {m['seed_disagreement_B3_pct']} |")
    md = "\n".join(lines) + "\n"
    open(os.path.join(RESULTS, "seed_variance.md"), "w").write(md)

    # Console summary
    print(md)
    sds_b0 = [per_model[m]["B0_RiskyAcc_SD"] for m in per_model if per_model[m]["n_seeds"] > 1]
    sds_b3 = [per_model[m]["B3_RiskyAcc_SD"] for m in per_model if per_model[m]["n_seeds"] > 1]
    dis_b0 = [per_model[m]["seed_disagreement_B0_pct"] for m in per_model if per_model[m]["seed_disagreement_B0_pct"] is not None]
    dis_b3 = [per_model[m]["seed_disagreement_B3_pct"] for m in per_model if per_model[m]["seed_disagreement_B3_pct"] is not None]
    if sds_b0:
        print(f"max B0 RiskyAcc SD = {max(sds_b0)}pp ; max B3 RiskyAcc SD = {max(sds_b3)}pp")
    if dis_b0:
        print(f"seed-disagreement B0 = {min(dis_b0)}-{max(dis_b0)}% ; B3 = {min(dis_b3)}-{max(dis_b3)}%")
    print("skipped:", skipped)


if __name__ == "__main__":
    main()

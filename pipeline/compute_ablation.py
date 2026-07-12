"""
Stage ablation for Table 5: re-run guard with B3_no_S{1,3,5,6} modes on
existing result.json files (no LLM re-run needed).

For each result.json:
  - dep_changes:   from result.json
  - evidence_refs: from bench/{FX_*}/task_{id}/evidence_refs.json
  - policy:        from bench/{FX_*}/task_{id}/dependency_policy.yaml
  - func/safety:   from result.json adjudication (pre-computed)

Outputs:
  results/ablation_stats.json   — aggregated per-model per-mode per-family
  results/ablation_raw.jsonl    — per-run row (for debugging)
"""

import argparse
import json
import yaml
from pathlib import Path
from collections import defaultdict

from .guard.decision import run_guard
from .adjudicator.metric_calculator import compute as compute_metrics


ABLATION_MODES = ["B3_no_S1", "B3_no_S2", "B3_no_S3", "B3_no_S4", "B3_no_S5", "B3_no_S6"]

FAMILY_ORDER  = ["F1", "F2", "F3", "F4", "F5", "F6"]

MODEL_DISPLAY = {
    "Qwen2.5-Coder-7B-Instruct":    "Qwen-7B",
    "Qwen2.5-Coder-14B-Instruct-AWQ": "Qwen-14B",
    "Qwen2.5-Coder-32B-Instruct-AWQ": "Qwen-32B",
    "deepseek-coder-6.7b-instruct": "DeepSeek-6.7B",
    "CodeLlama-7b-Instruct-hf":     "CodeLlama-7B",
}

FAMILY_STAGE_MAP = {
    "F1": "S1",  # package nonexistent/typosquat → caught by S1
    "F2": "S2",  # version validity              → caught by S2
    "F3": "S3",  # direct CVE                    → caught by S3
    "F4": "S5",  # license policy                → caught by S5
    "F5": "S4",  # transitive vuln               → caught by S4
    "F6": "S6",  # unnecessary dep               → caught by S6
}


def _bench_task_dir(bench_root: Path, task_id: str) -> Path | None:
    fam = task_id.split("_")[1]  # task_F1_012 → F1
    fam_dirs = [d for d in bench_root.iterdir() if d.name.startswith(fam + "_")]
    if not fam_dirs:
        return None
    return fam_dirs[0] / task_id


def _load_bench(bench_root: Path, task_id: str):
    td = _bench_task_dir(bench_root, task_id)
    if not td or not td.exists():
        return None, None
    ev_path = td / "evidence_refs.json"
    po_path = td / "dependency_policy.yaml"
    evidence_refs = json.loads(ev_path.read_text()) if ev_path.exists() else {}
    policy = yaml.safe_load(po_path.read_text()) if po_path.exists() else {}
    return evidence_refs, policy


def collect_runs(results_dir: Path) -> list[dict]:
    from .config import is_canonical_run
    by_key = {}
    for p in results_dir.glob("task_*/*/result.json"):
        if not is_canonical_run(p.parent.name):   # deterministic: canonical run only
            continue
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        if "metrics_by_mode" not in r:
            continue
        key = (r["task_id"], r["generation_condition"],
               r.get("model_id", "").rsplit("/", 1)[-1])
        mtime = p.stat().st_mtime
        if key not in by_key or mtime > by_key[key]["_mtime"]:
            r["_mtime"] = mtime
            r["_path"] = str(p)
            by_key[key] = r
    return list(by_key.values())


def run_ablation_for_result(r: dict, bench_root: Path) -> dict | None:
    task_id   = r["task_id"]
    dep_changes = r.get("dep_changes") or []

    evidence_refs, policy = _load_bench(bench_root, task_id)
    if evidence_refs is None:
        return None

    adj = r.get("adjudication", {})
    func_result   = adj.get("functional", {})
    safety_result = adj.get("safety", {})
    if not func_result or not safety_result:
        return None

    ablation = {}
    for mode in ABLATION_MODES:
        guard_res = run_guard(dep_changes, evidence_refs, policy, mode=mode)
        metrics   = compute_metrics(func_result, safety_result, guard_res)
        ablation[mode] = {
            "guard_decision": guard_res["decision"],
            "metrics": metrics,
        }

    return ablation


def aggregate(rows: list[dict]) -> dict:
    """
    rows: list of {model, family, cond, ablation: {mode: {guard_decision, metrics}}}
    Returns nested dict: model → mode → family → {n, risky_acc, false_block, false_allow, block_rate}
    """
    # model → mode → family → counters
    counts = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))

    for row in rows:
        model  = row["model"]
        family = row["family"]
        abl    = row["ablation"]
        for mode, data in abl.items():
            m = data["metrics"]
            acc = m.get("accepted", {})
            gd  = m.get("guard_metrics", {})
            pa  = acc.get("patch_accepted")

            counts[model][mode][family]["n"] += 1
            if acc.get("risky_accepted_patch"):
                counts[model][mode][family]["risky_acc"] += 1
            if gd.get("false_block"):
                counts[model][mode][family]["false_block"] += 1
            if gd.get("false_allow"):
                counts[model][mode][family]["false_allow"] += 1
            if pa is False:
                counts[model][mode][family]["blocked"] += 1

    # Convert to rates
    result = {}
    for model, modes in counts.items():
        result[model] = {}
        for mode, families in modes.items():
            result[model][mode] = {}
            # per-family
            for fam, c in families.items():
                n = c["n"]
                result[model][mode][fam] = {
                    "n": n,
                    "risky_acc_rate":   c["risky_acc"]   / n if n else None,
                    "false_block_rate": c["false_block"]  / n if n else None,
                    "false_allow_rate": c["false_allow"]  / n if n else None,
                    "block_rate":       c["blocked"]      / n if n else None,
                    "k_risky":          c["risky_acc"],
                    "k_false_block":    c["false_block"],
                }
            # overall
            tot_n = tot_r = tot_fb = tot_fa = tot_bl = 0
            for fam, c in families.items():
                tot_n  += c["n"]
                tot_r  += c["risky_acc"]
                tot_fb += c["false_block"]
                tot_fa += c["false_allow"]
                tot_bl += c["blocked"]
            result[model][mode]["Overall"] = {
                "n": tot_n,
                "risky_acc_rate":   tot_r  / tot_n if tot_n else None,
                "false_block_rate": tot_fb / tot_n if tot_n else None,
                "false_allow_rate": tot_fa / tot_n if tot_n else None,
                "block_rate":       tot_bl / tot_n if tot_n else None,
                "k_risky":          tot_r,
                "k_false_block":    tot_fb,
            }
    return result


def latex_table5(b3_stats: dict, ablation_stats: dict) -> str:
    """
    Table 5: Stage ablation.
    Rows: B3 (full), B3_no_S1, B3_no_S3, B3_no_S5, B3_no_S6
    Cols: Model | Mode | RiskyAcc-Overall | ΔRiskyAcc vs B3 | per-family miss rate
    """
    mode_labels = {
        "B3":       "B3 (full)",
        "B3_no_S1": "B3 $-$S1",
        "B3_no_S2": "B3 $-$S2",
        "B3_no_S3": "B3 $-$S3",
        "B3_no_S4": "B3 $-$S4",
        "B3_no_S5": "B3 $-$S5",
        "B3_no_S6": "B3 $-$S6",
    }
    # Family → primary stage mapping for column header
    fam_stage = ["F1/S1", "F2/S2", "F3/S3", "F4/S5", "F5/S4", "F6/S6"]

    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{Stage ablation: RiskyAcc rate when one guard stage is removed.",
        r"    B3 (full) is the baseline; $\Delta$ = ablation $-$ B3 (pp increase in missed risks).",
        r"    Family columns show per-family RiskyAcc under each ablation.}",
        r"  \label{tab:ablation}",
        r"  \setlength{\tabcolsep}{3pt}",
        r"  \resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{l l r r r r r r r r}",
        r"    \toprule",
        r"    Model & Mode & Overall & $\Delta$ & F1/S1 & F2/S2 & F3/S3 & F4/S5 & F5/S4 & F6/S6 \\",
        r"    \midrule",
    ]

    models = list(ablation_stats.keys())
    for mi, model in enumerate(models):
        abl = ablation_stats[model]
        b3  = b3_stats.get(model, {})

        # B3 overall from b3_stats
        b3_overall = b3.get("Overall", {})
        b3_rate = b3_overall.get("risky_acc_rate")

        show_modes = ["B3"] + ABLATION_MODES
        for ki, mode in enumerate(show_modes):
            label = model if ki == 0 else ""
            ml = mode_labels.get(mode, mode)

            if mode == "B3":
                data = b3.get("Overall", {})
                overall_rate = data.get("risky_acc_rate")
                fam_rates = [b3.get(fam, {}).get("risky_acc_rate") for fam in FAMILY_ORDER]
                delta_str = "—"
            else:
                data = abl.get(mode, {}).get("Overall", {})
                overall_rate = data.get("risky_acc_rate")
                fam_rates = [abl.get(mode, {}).get(fam, {}).get("risky_acc_rate") for fam in FAMILY_ORDER]
                if overall_rate is not None and b3_rate is not None:
                    delta = (overall_rate - b3_rate) * 100
                    delta_str = f"$+{delta:.1f}$" if delta >= 0 else f"${delta:.1f}$"
                else:
                    delta_str = "—"

            overall_str = f"{100*overall_rate:.1f}\\%" if overall_rate is not None else "—"
            fam_strs = [f"{100*v:.0f}\\%" if v is not None else "—" for v in fam_rates]

            row_parts = [label, ml, overall_str, delta_str] + fam_strs
            lines.append("    " + " & ".join(row_parts) + r" \\")

        lines.append(r"    \midrule")

    lines[-1] = r"    \bottomrule"
    lines += [
        r"  \end{tabular}",
        r"  }",
        r"\end{table}",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", type=Path, default=Path("results"))
    ap.add_argument("--bench-root",  type=Path, default=Path("bench"))
    ap.add_argument("--output-json", type=Path, default=Path("results/ablation_stats.json"))
    ap.add_argument("--output-latex", type=Path, default=Path("results/ablation_table.tex"))
    ap.add_argument("--output-raw",  type=Path, default=Path("results/ablation_raw.jsonl"))
    args = ap.parse_args()

    print("Collecting runs...")
    runs = collect_runs(args.results_dir)
    print(f"  {len(runs)} deduplicated runs")

    # Also load B3 stats from existing metrics_by_mode for comparison
    b3_by_model = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    rows = []
    errors = 0
    for i, r in enumerate(runs):
        if i % 500 == 0:
            print(f"  Processing {i}/{len(runs)}...")

        model_slug = r.get("model_id", "").rsplit("/", 1)[-1]
        model = MODEL_DISPLAY.get(model_slug, model_slug)
        task_id = r["task_id"]
        family = task_id.split("_")[1]

        # B3 stats from existing data
        mm = r.get("metrics_by_mode", {}).get("B3", {})
        b3_by_model[model][family]["n"] += 1
        if mm.get("accepted", {}).get("risky_accepted_patch"):
            b3_by_model[model][family]["risky_acc"] += 1
        if mm.get("guard_metrics", {}).get("false_block"):
            b3_by_model[model][family]["false_block"] += 1
        if mm.get("accepted", {}).get("patch_accepted") is False:
            b3_by_model[model][family]["blocked"] += 1

        # Ablation
        ablation = run_ablation_for_result(r, args.bench_root)
        if ablation is None:
            errors += 1
            continue

        rows.append({
            "model": model,
            "family": family,
            "cond": r.get("generation_condition"),
            "task_id": task_id,
            "ablation": ablation,
        })

    print(f"  Done. {len(rows)} successful, {errors} errors (missing bench data)")

    # Write raw
    with args.output_raw.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {args.output_raw}")

    # Build B3 stats in same format as ablation
    b3_stats_by_model = {}
    for model, families in b3_by_model.items():
        b3_stats_by_model[model] = {}
        tot = defaultdict(int)
        for fam, c in families.items():
            n = c["n"]
            b3_stats_by_model[model][fam] = {
                "n": n,
                "risky_acc_rate":   c["risky_acc"] / n if n else None,
                "false_block_rate": c["false_block"] / n if n else None,
                "block_rate":       c["blocked"] / n if n else None,
                "k_risky": c["risky_acc"],
            }
            for k, v in c.items():
                tot[k] += v
        n_tot = tot["n"]
        b3_stats_by_model[model]["Overall"] = {
            "n": n_tot,
            "risky_acc_rate":   tot["risky_acc"] / n_tot if n_tot else None,
            "false_block_rate": tot["false_block"] / n_tot if n_tot else None,
            "block_rate":       tot["blocked"] / n_tot if n_tot else None,
            "k_risky": tot["risky_acc"],
        }

    ablation_agg = aggregate(rows)

    stats = {
        "b3_baseline": b3_stats_by_model,
        "ablation": ablation_agg,
    }
    args.output_json.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"Wrote {args.output_json}")

    latex = latex_table5(b3_stats_by_model, ablation_agg)
    args.output_latex.write_text(latex)
    print(f"Wrote {args.output_latex}")

    # Print summary
    print("\n=== Ablation Summary (Overall RiskyAcc) ===")
    for model in b3_stats_by_model:
        b3r = b3_stats_by_model[model]["Overall"]["risky_acc_rate"]
        print(f"\n{model}: B3={100*b3r:.1f}%")
        for mode in ABLATION_MODES:
            abl_r = ablation_agg.get(model, {}).get(mode, {}).get("Overall", {}).get("risky_acc_rate")
            if abl_r is not None:
                delta = (abl_r - b3r) * 100
                print(f"  {mode}: {100*abl_r:.1f}%  (Δ={delta:+.1f}pp)")


if __name__ == "__main__":
    main()

"""
TSE-grade statistics for Tables 2, 3, 4.

Table 2: Wilson 95% CI per cell (family × model, B0 RiskyAcc)
Table 3: per-model McNemar p (G0 vs G1, SafetyPass-Core), SafetyPass-All, Δ columns
Table 4: operational metrics — BlockRate, AcceptedFunctionalSafePatch,
         FunctionalButBlockedPatch, DeveloperInterruptionRate

Output: results/tse_stats.json
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
from collections import defaultdict
from scipy.stats import binomtest


FAMILY_ORDER = ["F1", "F2", "F3", "F4", "F5", "F6"]

MODEL_DISPLAY = {
    "Qwen2.5-Coder-7B-Instruct": "Qwen-7B",
    "Qwen2.5-Coder-14B-Instruct-AWQ": "Qwen-14B",
    "Qwen2.5-Coder-32B-Instruct-AWQ": "Qwen-32B",
    "deepseek-coder-6.7b-instruct": "DeepSeek-6.7B",
    "CodeLlama-7b-Instruct-hf": "CodeLlama-7B",
}


# ── helpers ────────────────────────────────────────────────────────────────

def wilson_ci(k, n, z=1.96):
    """Wilson score 95% CI. Returns (lo, hi) as fractions."""
    if n == 0:
        return (None, None)
    p = k / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def mcnemar_exact(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return binomtest(k, n, p=0.5).pvalue


def fmt_pct(x, n=None):
    if x is None:
        return "—"
    s = f"{100*x:.1f}\\%"
    if n is not None:
        s += f" ({n})"
    return s


def fmt_ci(lo, hi):
    if lo is None:
        return "—"
    return f"[{100*lo:.0f}–{100*hi:.0f}]"


# ── data collection ─────────────────────────────────────────────────────────

def load_runs_jsonl(path: Path) -> list[dict]:
    """Load strict-offline canonical run rows from JSONL."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _run_model_slug(run: dict) -> str:
    return str(run.get("model_id", "")).rsplit("/", 1)[-1]


_REQUIRED_JSONL_MODES = ("B0", "B3")
_REQUIRED_ACCEPTED_FIELDS = {
    "patch_accepted": bool,
    "functional_success": (bool, type(None)),
    "safety_pass_core": (bool, type(None)),
    "risk_adjusted_success_core": (bool, type(None)),
    "risky_accepted_patch": bool,
}
_REQUIRED_GENERATED_FIELDS = {
    "functional_success": bool,
    "safety_pass_core": bool,
    "risk_adjusted_success_core": bool,
}
_REQUIRED_GUARD_METRIC_FIELDS = {
    "false_block": bool,
    "false_allow": bool,
}


def _validate_jsonl_metric_cell(row: dict, mode: str, row_index: int) -> None:
    metrics = (row.get("metrics_by_mode") or {}).get(mode)
    if not isinstance(metrics, dict):
        raise ValueError(f"JSONL row {row_index} missing metrics_by_mode.{mode}")

    sections = {
        "accepted": _REQUIRED_ACCEPTED_FIELDS,
        "generated": _REQUIRED_GENERATED_FIELDS,
        "guard_metrics": _REQUIRED_GUARD_METRIC_FIELDS,
    }
    for section, fields in sections.items():
        values = metrics.get(section)
        if not isinstance(values, dict):
            raise ValueError(f"JSONL row {row_index} missing metrics_by_mode.{mode}.{section}")
        for field, expected_type in fields.items():
            if field not in values:
                raise ValueError(
                    f"JSONL row {row_index} missing metrics_by_mode.{mode}.{section}.{field}"
                )
            if not isinstance(values[field], expected_type):
                raise ValueError(
                    f"JSONL row {row_index} invalid type for "
                    f"metrics_by_mode.{mode}.{section}.{field}: {values[field]!r}"
                )


def _validate_jsonl_run(row: dict, row_index: int) -> None:
    if not isinstance(row.get("metrics_by_mode"), dict):
        raise ValueError(f"JSONL row {row_index} missing metrics_by_mode")
    for mode in _REQUIRED_JSONL_MODES:
        _validate_jsonl_metric_cell(row, mode, row_index)


def collect_runs_from_jsonl(path: Path, model_slug: str) -> list[dict]:
    """Collect canonical rows for one model from a strict-offline JSONL file."""
    runs = []
    for index, row in enumerate(load_runs_jsonl(path), start=1):
        slug = _run_model_slug(row)
        if slug != model_slug:
            continue
        _validate_jsonl_run(row, index)
        runs.append(row)
    return runs


def collect_runs(
    results_dir: Path,
    model_slug: str,
    runs_jsonl: Path | None = None,
) -> list[dict]:
    if runs_jsonl is not None:
        return collect_runs_from_jsonl(runs_jsonl, model_slug)

    from .config import is_canonical_run
    by_key = {}
    for p in results_dir.glob("task_*/*/result.json"):
        if not is_canonical_run(p.parent.name):   # deterministic: canonical run only
            continue
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        slug = r.get("model_id", "").rsplit("/", 1)[-1]
        if model_slug not in slug:
            continue
        if "metrics_by_mode" not in r:
            continue
        key = (r["task_id"], r["generation_condition"])
        mtime = p.stat().st_mtime
        if key not in by_key or mtime > by_key[key]["_mtime"]:
            r["_mtime"] = mtime
            by_key[key] = r
    return list(by_key.values())


def mode_val(r, mode, *path):
    cur = r.get("metrics_by_mode", {}).get(mode, {})
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def safety_pass_all(r):
    """True iff adjudication.safety.risk_labels is empty (no risk at all)."""
    labels = r.get("adjudication", {}).get("safety", {}).get("risk_labels", None)
    if labels is None:
        return None
    return len(labels) == 0


# ── Table 2: Wilson CI ───────────────────────────────────────────────────────

def compute_table2(runs_by_model):
    result = {}
    for slug, runs in runs_by_model.items():
        model_name = MODEL_DISPLAY.get(slug, slug)
        result[model_name] = {}
        for fam in FAMILY_ORDER:
            fam_runs = [r for r in runs if r["task_id"].split("_")[1] == fam]
            k = sum(1 for r in fam_runs
                    if mode_val(r, "B0", "accepted", "risky_accepted_patch"))
            n = len(fam_runs)
            lo, hi = wilson_ci(k, n)
            result[model_name][fam] = {
                "k": k, "n": n,
                "rate": k / n if n else None,
                "ci_lo": lo, "ci_hi": hi,
            }
        # overall
        k = sum(1 for r in runs
                if mode_val(r, "B0", "accepted", "risky_accepted_patch"))
        n = len(runs)
        lo, hi = wilson_ci(k, n)
        result[model_name]["Overall"] = {
            "k": k, "n": n,
            "rate": k / n if n else None,
            "ci_lo": lo, "ci_hi": hi,
        }
    return result


# ── Table 3: G0 vs G1, McNemar, SafetyPass-All ──────────────────────────────

def compute_table3(runs_by_model):
    result = {}
    for slug, runs in runs_by_model.items():
        model_name = MODEL_DISPLAY.get(slug, slug)
        result[model_name] = {}
        for cond in ("G0", "G1"):
            cond_runs = [r for r in runs if r["generation_condition"] == cond]
            if not cond_runs:
                continue
            n = len(cond_runs)

            fs   = sum(1 for r in cond_runs if mode_val(r,"B3","generated","functional_success"))
            spc  = sum(1 for r in cond_runs if mode_val(r,"B3","generated","safety_pass_core"))
            ras  = sum(1 for r in cond_runs if mode_val(r,"B3","generated","risk_adjusted_success_core"))
            ra   = sum(1 for r in cond_runs if mode_val(r,"B3","accepted","risky_accepted_patch"))
            stdlib= sum(1 for r in cond_runs if r.get("agent_behavior", {}).get("stdlib_only"))

            # SafetyPass-All
            spa_vals = [safety_pass_all(r) for r in cond_runs]
            spa = sum(1 for v in spa_vals if v is True)
            spa_n = sum(1 for v in spa_vals if v is not None)

            result[model_name][cond] = {
                "n": n,
                "func_succ": fs / n,
                "safety_core": spc / n,
                "safety_all": spa / spa_n if spa_n else None,
                "safety_all_n": spa_n,
                "ras": ras / n,
                "risky_acc": ra / n,
                "stdlib_only": stdlib / n,
            }

        # McNemar: G0 vs G1, safety_pass_core (paired by task_id)
        g0 = {r["task_id"]: r for r in runs if r["generation_condition"] == "G0"}
        g1 = {r["task_id"]: r for r in runs if r["generation_condition"] == "G1"}
        common = sorted(set(g0) & set(g1))
        b = c = 0  # b: G0=1,G1=0; c: G0=0,G1=1
        for tid in common:
            v0 = mode_val(g0[tid], "B3", "generated", "safety_pass_core")
            v1 = mode_val(g1[tid], "B3", "generated", "safety_pass_core")
            if v0 is None or v1 is None:
                continue
            if v0 and not v1:
                b += 1
            elif v1 and not v0:
                c += 1
        p = mcnemar_exact(b, c)
        # delta: G1 - G0
        if "G0" in result[model_name] and "G1" in result[model_name]:
            delta_sc = result[model_name]["G1"]["safety_core"] - result[model_name]["G0"]["safety_core"]
            delta_fs = result[model_name]["G1"]["func_succ"]   - result[model_name]["G0"]["func_succ"]
        else:
            delta_sc = delta_fs = None
        result[model_name]["mcnemar"] = {
            "n_common": len(common), "b": b, "c": c,
            "p_value": round(p, 4),
            "delta_safety_core": round(delta_sc * 100, 1) if delta_sc is not None else None,
            "delta_func_succ":   round(delta_fs * 100, 1) if delta_fs is not None else None,
        }
    return result


# ── Table 4: operational metrics ─────────────────────────────────────────────

def compute_table4(runs_by_model):
    result = {}
    modes = ("B0", "B1", "B2", "B3", "R1")
    for slug, runs in runs_by_model.items():
        model_name = MODEL_DISPLAY.get(slug, slug)
        result[model_name] = {}
        for mode in modes:
            n = len(runs)
            if n == 0:
                continue

            # existing metrics
            fs   = sum(1 for r in runs if mode_val(r, mode, "generated", "functional_success"))
            spc  = sum(1 for r in runs if mode_val(r, mode, "generated", "safety_pass_core"))
            ra   = sum(1 for r in runs if mode_val(r, mode, "accepted", "risky_accepted_patch"))
            fb   = sum(1 for r in runs if mode_val(r, mode, "guard_metrics", "false_block"))
            fa   = sum(1 for r in runs if mode_val(r, mode, "guard_metrics", "false_allow"))

            # operational metrics
            # BlockRate: fraction where patch was NOT accepted (guard blocked it)
            patch_accepted_vals = [mode_val(r, mode, "accepted", "patch_accepted") for r in runs]
            n_blocked = sum(1 for v in patch_accepted_vals if v is False)
            n_pa_valid = sum(1 for v in patch_accepted_vals if v is not None)
            block_rate = n_blocked / n_pa_valid if n_pa_valid else None

            # AcceptedFunctionalSafePatch: accepted AND functional AND safe
            afsp = sum(
                1 for r in runs
                if (mode_val(r, mode, "accepted", "patch_accepted") is True
                    and mode_val(r, mode, "accepted", "functional_success") is True
                    and mode_val(r, mode, "accepted", "safety_pass_core") is True)
            )

            # FunctionalButBlockedPatch = false_block (blocked despite being functionally OK and safe)
            # DeveloperInterruptionRate = false_block rate
            dev_interrupt_rate = fb / n

            # R1 repair metrics
            repair_attempted  = sum(1 for r in runs if mode_val(r, mode, "repair_metrics", "attempted"))
            repair_unblocked  = sum(1 for r in runs if mode_val(r, mode, "repair_metrics", "unblocked"))
            repair_func_recov = sum(1 for r in runs if mode_val(r, mode, "repair_metrics", "functional_recovered"))
            repair_safe_recov = sum(1 for r in runs if mode_val(r, mode, "repair_metrics", "safety_recovered"))

            result[model_name][mode] = {
                "n": n,
                "func_succ": fs / n,
                "safety_core": spc / n,
                "risky_acc": ra / n,
                "false_block": fb / n,
                "false_allow": fa / n,
                "block_rate": block_rate,
                "accepted_functional_safe": afsp / n,
                "functional_but_blocked": fb / n,  # = false_block
                "developer_interruption_rate": dev_interrupt_rate,
                "repair": {
                    "attempted": repair_attempted,
                    "unblocked": repair_unblocked,
                    "functional_recovered": repair_func_recov,
                    "safety_recovered": repair_safe_recov,
                },
            }
    return result


# ── LaTeX generation ─────────────────────────────────────────────────────────

def latex_table2(t2):
    models = list(t2.keys())
    header = " & ".join(["Family"] + models)
    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{RQ1 --- B0 risk-presence rate by task family and model",
        r"    (40 runs per cell). Wilson 95\% CI shown in brackets.}",
        r"  \label{tab:rq1}",
        r"  \setlength{\tabcolsep}{3pt}",
        r"  \resizebox{\columnwidth}{!}{%",
        r"\begin{tabular}{l " + "r " * len(models) + r"}",
        r"    \toprule",
        f"    {header} \\\\",
        r"    \midrule",
    ]
    for fam in FAMILY_ORDER:
        cells = [fam]
        for m in models:
            d = t2[m][fam]
            k, n, lo, hi = d["k"], d["n"], d["ci_lo"], d["ci_hi"]
            pct = f"{100*d['rate']:.0f}\\%"
            ci = f"[{100*lo:.0f}--{100*hi:.0f}]" if lo is not None else ""
            cells.append(f"{pct} ({k}/{n}) {ci}")
        lines.append("    " + " & ".join(cells) + r" \\")
    lines.append(r"    \midrule")
    # overall
    cells = [r"\textbf{Overall}"]
    for m in models:
        d = t2[m]["Overall"]
        k, n, lo, hi = d["k"], d["n"], d["ci_lo"], d["ci_hi"]
        pct = f"\\textbf{{{100*d['rate']:.1f}\\%}}"
        ci = f"[{100*lo:.0f}--{100*hi:.0f}]" if lo is not None else ""
        cells.append(f"{pct} ({k}/{n}) {ci}")
    lines.append("    " + " & ".join(cells) + r" \\")
    lines += [
        r"    \bottomrule",
        r"  \end{tabular}",
        r"  }",
        r"\end{table}",
    ]
    return "\n".join(lines)


def latex_table3(t3):
    models = list(t3.keys())
    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{RQ2 --- G0 vs.\ G1 under B3 guard (120 runs per cell).",
        r"    $\Delta$ = G1$-$G0 (pp). SafetyPass-All = zero risk labels.",
        r"    McNemar exact $p$ for SafetyPass-Core.}",
        r"  \label{tab:rq2}",
        r"  \setlength{\tabcolsep}{3.5pt}",
        r"  \resizebox{\columnwidth}{!}{%",
        r"\begin{tabular}{l c r r r r r r r}",
        r"    \toprule",
        r"    Model & Cond & FuncSucc & $\Delta$FS & SafetyPass-Core & SafetyPass-All & $\Delta$SP & RiskyAcc & McNemar $p$ \\",
        r"    \midrule",
    ]
    for model in models:
        md = t3[model]
        mcn = md.get("mcnemar", {})
        p = mcn.get("p_value")
        dsp = mcn.get("delta_safety_core")
        dfs = mcn.get("delta_func_succ")
        p_str = f"\\textbf{{{p:.4f}}}" if p is not None and p < 0.05 else (f"{p:.4f}" if p is not None else "—")

        for ci, cond in enumerate(("G0", "G1")):
            if cond not in md:
                continue
            d = md[cond]
            fs_str  = f"{100*d['func_succ']:.1f}\\%"
            spc_str = f"{100*d['safety_core']:.1f}\\%"
            spa_str = f"{100*d['safety_all']:.1f}\\%" if d['safety_all'] is not None else "—"
            ra_str  = f"{100*d['risky_acc']:.1f}\\%"

            if cond == "G0":
                delta_fs_str = "—"
                delta_sp_str = "—"
                p_col = "—"
            else:
                delta_fs_str = (f"$+{dfs:.1f}$" if dfs and dfs >= 0 else f"${dfs:.1f}$") if dfs is not None else "—"
                delta_sp_str = (f"$+{dsp:.1f}$" if dsp and dsp >= 0 else f"${dsp:.1f}$") if dsp is not None else "—"
                p_col = p_str

            row = f"    {model if ci == 0 else ''} & {cond} & {fs_str} & {delta_fs_str} & {spc_str} & {spa_str} & {delta_sp_str} & {ra_str} & {p_col} \\\\"
            lines.append(row)
        lines.append(r"    \midrule")

    # remove last \midrule, replace with \bottomrule
    lines[-1] = r"    \bottomrule"
    lines += [
        r"  \end{tabular}",
        r"  }",
        r"\end{table}",
    ]
    return "\n".join(lines)


def latex_table4(t4):
    models = list(t4.keys())
    lines = [
        r"\begin{table}[t]",
        r"  \centering",
        r"  \caption{RQ3 --- Block-condition gradient with operational metrics.",
        r"    AFSP = AcceptedFunctional\-SafePatch; DIR = DeveloperInterruptionRate (false-block rate).}",
        r"  \label{tab:rq3}",
        r"  \setlength{\tabcolsep}{3pt}",
        r"  \resizebox{\columnwidth}{!}{%",
        r"\begin{tabular}{l l r r r r r r r}",
        r"    \toprule",
        r"    Model & Mode & FuncSucc & SafetyPass & RiskyAcc & BlockRate & AFSP & DIR & FalseAllow \\",
        r"    \midrule",
    ]
    for mi, model in enumerate(models):
        md = t4[model]
        show_modes = ("B0", "B3", "R1") if "R1" in md else ("B0", "B3")
        for ki, mode in enumerate(show_modes):
            if mode not in md:
                continue
            d = md[mode]
            fs   = f"{100*d['func_succ']:.1f}\\%"
            spc  = f"{100*d['safety_core']:.1f}\\%"
            ra   = f"{100*d['risky_acc']:.1f}\\%"
            br   = f"{100*d['block_rate']:.1f}\\%" if d['block_rate'] is not None else "—"
            afsp = f"{100*d['accepted_functional_safe']:.1f}\\%"
            dir_ = f"{100*d['developer_interruption_rate']:.1f}\\%"
            fa   = f"{100*d['false_allow']:.1f}\\%"
            label = model if ki == 0 else ""
            multi = f"\\multirow{{{len(show_modes)}}}{{*}}{{{model}}}" if ki == 0 else ""
            lines.append(f"      {label} & {mode} & {fs} & {spc} & {ra} & {br} & {afsp} & {dir_} & {fa} \\\\")
        lines.append(r"    \midrule")

    lines[-1] = r"    \bottomrule"
    lines += [
        r"  \end{tabular}",
        r"  }",
        r"\end{table}",
    ]
    return "\n".join(lines)


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", type=Path, default=Path("results"))
    ap.add_argument("--runs-jsonl", type=Path, default=None)
    ap.add_argument("--output-json", type=Path, default=Path("results/tse_stats.json"))
    ap.add_argument("--output-latex", type=Path, default=Path("results/tse_tables.tex"))
    args = ap.parse_args()

    runs_by_model = {}
    for slug in MODEL_DISPLAY:
        runs = collect_runs(args.results_dir, slug, runs_jsonl=args.runs_jsonl)
        if runs:
            runs_by_model[slug] = runs
            print(f"  {slug}: {len(runs)} runs")

    # Integrity guard: 0 runs → empty tables written + printed with EXIT 0, a
    # silent false positive. Per-run result.json under results/task_*/ is
    # gitignored and ships only in the artifact ZIP, so a bare git clone has 0
    # runs here. Fail loudly rather than emit empty tables as if successful.
    if sum(len(r) for r in runs_by_model.values()) == 0:
        import sys
        source = (
            f"{args.runs_jsonl}"
            if args.runs_jsonl
            else f"{args.results_dir}/task_*/"
        )
        print(
            f"\nERROR: collected 0 per-run results from {source}.\n"
            "  These files are gitignored and are NOT in a bare git clone.\n"
            "  Run from the unpacked artifact ZIP or a populated working tree.",
            file=sys.stderr,
        )
        sys.exit(2)

    t2 = compute_table2(runs_by_model)
    t3 = compute_table3(runs_by_model)
    t4 = compute_table4(runs_by_model)

    stats = {"table2": t2, "table3": t3, "table4": t4}
    if args.runs_jsonl is not None:
        stats = {
            "evidence_regime": "strict_offline",
            "canonical_runs_sha256": hashlib.sha256(args.runs_jsonl.read_bytes()).hexdigest(),
            **stats,
        }
    args.output_json.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    print(f"Wrote {args.output_json}")

    latex = "\n\n% ─────────────────────────────────────\n\n".join([
        "% TSE Tables 2, 3, 4 — auto-generated by pipeline/compute_tse_stats.py\n",
        latex_table2(t2),
        latex_table3(t3),
        latex_table4(t4),
    ])
    args.output_latex.write_text(latex)
    print(f"Wrote {args.output_latex}")

    # Print summary for quick review
    print("\n=== Table 2 summary (Overall, Wilson CI) ===")
    for m, v in t2.items():
        d = v["Overall"]
        print(f"  {m}: {100*d['rate']:.1f}% ({d['k']}/{d['n']}) [{100*d['ci_lo']:.0f}–{100*d['ci_hi']:.0f}]")

    print("\n=== Table 3 McNemar (G0 vs G1, SafetyPass-Core, B3) ===")
    for m, v in t3.items():
        mcn = v.get("mcnemar", {})
        print(f"  {m}: Δ={mcn.get('delta_safety_core')} pp, p={mcn.get('p_value')}, "
              f"n_common={mcn.get('n_common')}, b={mcn.get('b')}, c={mcn.get('c')}")

    print("\n=== Table 4 BlockRate + AFSP (B3) ===")
    for m, v in t4.items():
        if "B3" in v:
            d = v["B3"]
            print(f"  {m}: BlockRate={100*d['block_rate']:.1f}%, "
                  f"AFSP={100*d['accepted_functional_safe']:.1f}%, "
                  f"DIR={100*d['developer_interruption_rate']:.1f}%")


if __name__ == "__main__":
    main()

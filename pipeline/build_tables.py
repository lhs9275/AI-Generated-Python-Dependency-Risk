"""
Paper Table 1-5 자동 생성 (연구계획서 §17 기준).

Table 1: AgentSupplyBench-Py 구성
Table 2: RQ1 risk and interception stage (B0 baseline)
Table 3: RQ2 grounded vs ungrounded (G0 vs G1)
Table 4: RQ3 AgentSupplyGuard effect (B0~R1 by model)
Table 5: AIDev external validation

출력: markdown + LaTeX
"""

import argparse
import json
from pathlib import Path
from collections import defaultdict


FAMILY_NAMES = {
    "F1": ("Package existence", "PyPI metadata"),
    "F2": ("Version validity", "PyPI release/version metadata"),
    "F3": ("Direct vulnerability", "OSV/GitHub Advisory"),
    "F4": ("License policy", "license metadata + task policy"),
    "F5": ("Transitive vulnerability", "dependency graph + advisory"),
    "F6": ("Unnecessary dependency", "task design / dependency_policy"),
}

MODEL_DISPLAY = {
    "Qwen2.5-Coder-7B-Instruct": "Qwen2.5-Coder-7B",
    "Qwen2.5-Coder-14B-Instruct-AWQ": "Qwen2.5-Coder-14B",
    "Qwen2.5-Coder-32B-Instruct-AWQ": "Qwen2.5-Coder-32B",
    "deepseek-coder-6.7b-instruct": "DeepSeek-Coder-6.7B",
    "CodeLlama-7b-Instruct-hf": "CodeLlama-7B",
}


def collect_runs(results_dir: Path, model_slug_contains: str) -> list[dict]:
    try:
        from .config import is_canonical_run
    except ImportError:
        import re as _re
        _C = _re.compile(r"_G[01]_[0-9a-fA-F]+$")
        is_canonical_run = lambda n: bool(_C.search(n))
    by_key = {}
    for p in results_dir.glob("task_*/*/result.json"):
        if not is_canonical_run(p.parent.name):   # deterministic: canonical run only
            continue
        try:
            r = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        slug = r.get("model_id", "").rsplit("/", 1)[-1]
        if model_slug_contains not in slug:
            continue
        if "metrics_by_mode" not in r:
            continue
        key = (r["task_id"], r["generation_condition"])
        if key not in by_key or p.stat().st_mtime > by_key[key]["_mtime"]:
            r["_mtime"] = p.stat().st_mtime
            by_key[key] = r
    return list(by_key.values())


def _rate(runs, key_path):
    n = total = 0
    for r in runs:
        cur = r.get("metrics_by_mode", {}).get("B3" if "metrics_by_mode" not in key_path else "B0", r.get("metrics", {}))
        for k in key_path.split("."):
            cur = cur.get(k) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur is None:
            continue
        total += 1
        if cur:
            n += 1
    return (n / total) if total else None, total


def mode_rate(runs, mode, key_path):
    n = total = 0
    for r in runs:
        cur = r.get("metrics_by_mode", {}).get(mode, {})
        for k in key_path.split("."):
            cur = cur.get(k) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur is None:
            continue
        total += 1
        if cur:
            n += 1
    return n, total


def table1(bench_root: Path) -> str:
    lines = ["## Table 1. AgentSupplyBench-Py 구성", "",
             "| Family | Risk type | #Tasks | Primary/Secondary | PR-time evidence |",
             "|---|---|---:|---|---|"]
    for fam_code, (risk_type, ev) in FAMILY_NAMES.items():
        fam_dir = next(bench_root.glob(f"{fam_code}_*"), None)
        if not fam_dir:
            continue
        n = len(list(fam_dir.glob("task_*")))
        primary = "Primary" if fam_code != "F6" else "Secondary"
        lines.append(f"| {fam_code} | {risk_type} | {n} | {primary} | {ev} |")
    lines.append("")
    return "\n".join(lines)


def table2(runs_by_model: dict) -> str:
    """RQ1: B0 baseline 의 risk presence per family per model."""
    lines = ["## Table 2. RQ1 — Risk presence at B0 (no guard) by family",
             "",
             "각 family 에서 B0 (no guard) 시 발생한 risky_accepted_patch 비율.",
             ""]
    headers = ["Family"]
    for slug in runs_by_model:
        headers.append(MODEL_DISPLAY.get(slug, slug))
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for fam_code in FAMILY_NAMES:
        row = [fam_code]
        for slug, runs in runs_by_model.items():
            fam_runs = [r for r in runs if r["task_id"].split("_")[1] == fam_code]
            n, total = mode_rate(fam_runs, "B0", "accepted.risky_accepted_patch")
            row.append(f"{100*n/total:.0f}% ({n}/{total})" if total else "—")
        lines.append("| " + " | ".join(row) + " |")
    # overall row
    row = ["**Overall**"]
    for slug, runs in runs_by_model.items():
        n, total = mode_rate(runs, "B0", "accepted.risky_accepted_patch")
        row.append(f"**{100*n/total:.1f}%** ({n}/{total})" if total else "—")
    lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    return "\n".join(lines)


def table3(runs_by_model: dict) -> str:
    """RQ2: G0 vs G1 grounded vs ungrounded."""
    lines = ["## Table 3. RQ2 — G0 (ungrounded) vs G1 (grounded)",
             "",
             "G1 evidence-grounded prompt 가 functional/safety 에 미치는 영향. B3 mode 기준.",
             "",
             "| Model | Cond | FuncSucc | SafetyPass | RAS | RiskyAcc | stdlib_only |",
             "|---|---|---|---|---|---|---|"]
    for slug, runs in runs_by_model.items():
        for cond in ("G0", "G1"):
            cond_runs = [r for r in runs if r["generation_condition"] == cond]
            if not cond_runs:
                continue
            fs, total = mode_rate(cond_runs, "B3", "generated.functional_success")
            sp, _ = mode_rate(cond_runs, "B3", "generated.safety_pass_core")
            ras, _ = mode_rate(cond_runs, "B3", "generated.risk_adjusted_success_core")
            ra, _ = mode_rate(cond_runs, "B3", "accepted.risky_accepted_patch")
            stdlib = sum(1 for r in cond_runs if r.get("agent_behavior", {}).get("stdlib_only"))
            lines.append(
                f"| {MODEL_DISPLAY.get(slug, slug)} | {cond} | "
                f"{100*fs/total:.1f}% | {100*sp/total:.1f}% | {100*ras/total:.1f}% | "
                f"{100*ra/total:.1f}% | {100*stdlib/total:.0f}% |"
            )
    lines.append("")
    return "\n".join(lines)


def table4(runs_by_model: dict) -> str:
    """RQ3: Block-condition gradient by model."""
    lines = ["## Table 4. RQ3 — AgentSupplyGuard block-condition gradient",
             "",
             "각 모델의 B0/B1/B2/B3/R1 mode 별 RiskyAcc 및 FuncSucc.",
             ""]
    for slug, runs in runs_by_model.items():
        lines.append(f"### {MODEL_DISPLAY.get(slug, slug)} (n={len(runs)} runs)")
        lines.append("")
        lines.append("| Mode | FuncSucc | SafetyPass | RiskyAcc | FalseBlk | FalseAllow |")
        lines.append("|---|---|---|---|---|---|")
        for m in ("B0", "B1", "B2", "B3", "R1"):
            fs, _ = mode_rate(runs, m, "generated.functional_success")
            sp, _ = mode_rate(runs, m, "generated.safety_pass_core")
            ra, _ = mode_rate(runs, m, "accepted.risky_accepted_patch")
            fb, _ = mode_rate(runs, m, "guard_metrics.false_block")
            fa, _ = mode_rate(runs, m, "guard_metrics.false_allow")
            n = len(runs)
            lines.append(
                f"| {m} | {100*fs/n:.1f}% | {100*sp/n:.1f}% | {100*ra/n:.1f}% | "
                f"{100*fb/n:.1f}% | {100*fa/n:.1f}% |"
            )
        lines.append("")
    return "\n".join(lines)


def table5(aidev_eval_path: Path) -> str:
    # v3 경로 우선, 없으면 v2 fallback
    v3_path = aidev_eval_path.parent / "aidev_evaluation_v3.json"
    path = v3_path if v3_path.exists() else aidev_eval_path
    if not path.exists():
        return "## Table 5. AIDev external validation\n\n(no aidev evaluation file)\n"
    d = json.loads(path.read_text())
    is_v3 = d.get("version") == "v3"

    n = d["n_prs"]
    if is_v3:
        np_ = d["n_with_primary_risk"]
        ng = d["n_with_evidence_gap_only"]
        nt = d["n_true_negative"]
        rate_primary = d["primary_detection_rate"]
        rate_v2 = d["detection_rate_v2"]
        n_v2 = d["n_with_risk_v2"]
    else:
        np_ = d["n_with_risk"]
        rate_primary = np_ / n if n else 0

    lines = [
        "## Table 5. AIDev external validation",
        "",
        f"{n} dependency-changing agent-authored PRs (aider/codex/cursor/continue/devin/claude-code).",
        "Guard B3 적용; PR-time preventable risk presence (S1 package_nonexistent + S3 direct_vuln = primary).",
        "",
        "### Overall (primary = S1+S3 only)",
        f"| 지표 | 값 |",
        f"|---|---|",
        f"| Total PRs | **{n}** |",
        f"| PRs with **primary** risk (S1+S3) | **{np_} ({100*rate_primary:.1f}%)** ← paper main |",
    ]
    if is_v3:
        lines += [
            f"| PRs with evidence-gap only (S5 license_missing) | {ng} ({100*ng/n:.1f}%) ← excluded |",
            f"| True negative | {nt} ({100*nt/n:.1f}%) |",
            f"| v2 reported (incl. S5 noise) | {n_v2} ({100*rate_v2:.1f}%) |",
        ]
    lines.append("")

    lines += ["### By agent (primary risk)", "| Agent | Total | Primary risk | Gap-only |", "|---|---:|---:|---:|"]
    by_agent = d["by_agent"]
    for ag, v in sorted(by_agent.items()):
        if is_v3:
            pr_ = v["with_primary_risk"]
            gap = v["with_gap_only"]
            lines.append(f"| {ag} | {v['total']} | {pr_} ({100*pr_/v['total']:.0f}%) | {gap} |")
        else:
            wr = v["with_risk"]
            lines.append(f"| {ag} | {v['total']} | {wr} ({100*wr/v['total']:.0f}%) | — |")
    lines.append("")

    if is_v3:
        lines += ["### Primary label counts (S1+S3)", "| Risk label | n |", "|---|---:|"]
        for label, cnt in sorted(d["primary_label_counts"].items(), key=lambda x: -x[1]):
            lines.append(f"| {label} | {cnt} |")
        lines.append("")
        cav = d.get("caveat", {})
        lines.append(f"**Evidence-gap caveat**: {cav.get('evidence_gap', '')}")
        lines.append("")
        lines.append(f"**Temporal validity**: {cav.get('temporal_validity', '')}")
    else:
        lines.append("**Caveat**: license_missing 카운트는 우리 evidence_refs 에 metadata 부재로 인한 false signal.")
    lines.append("")
    return "\n".join(lines)


def table6(runs_by_model: dict) -> str:
    """Phase 1A: B1_scanner vs B1_deterministic, B2_scanner vs B2_deterministic."""
    lines = [
        "## Table 6. Phase 1A — Real scanner (pip-audit) vs Deterministic baseline",
        "",
        "B1/B2 scanner-based vs deterministic (evidence_refs-based). "
        "RiskyAcc = risky_accepted_patch rate; FalseBlk = false_block rate.",
        "",
        "| Model | Mode | RiskyAcc | FalseBlk | FalseAllow | n |",
        "|---|---|---|---|---|---:|",
    ]
    scanner_modes = ("B1_deterministic", "B1_scanner", "B2_deterministic", "B2_scanner")
    for slug, runs in runs_by_model.items():
        # scanner 결과가 있는 runs만 선별
        scanner_runs = [r for r in runs if "B1_scanner" in r.get("metrics_by_mode", {})]
        if not scanner_runs:
            continue
        label = MODEL_DISPLAY.get(slug, slug)
        for m in scanner_modes:
            ra, total = mode_rate(scanner_runs, m, "accepted.risky_accepted_patch")
            fb, _ = mode_rate(scanner_runs, m, "guard_metrics.false_block")
            fa, _ = mode_rate(scanner_runs, m, "guard_metrics.false_allow")
            if not total:
                continue
            lines.append(
                f"| {label} | {m} | {100*ra/total:.1f}% | "
                f"{100*fb/total:.1f}% | {100*fa/total:.1f}% | {total} |"
            )
    lines.append("")
    lines.append(
        "**Note**: B1_scanner = pip-audit (vuln only); "
        "B2_scanner = pip-audit + importlib.metadata license check. "
        "Deterministic = evidence_refs rule-based (S1+S3 / S1+S3+S5)."
    )
    lines.append("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", type=Path, default=Path("results"))
    p.add_argument("--bench-root", type=Path, default=Path("bench"))
    p.add_argument("--aidev-eval", type=Path, default=Path("results/aidev_evaluation_v3.json"))
    p.add_argument("--output", type=Path, default=Path("research_notes/paper_tables.md"))
    args = p.parse_args()

    runs_by_model = {}
    for slug in MODEL_DISPLAY:
        runs = collect_runs(args.results_dir, slug)
        if runs:
            runs_by_model[slug] = runs
            print(f"  {slug}: {len(runs)} runs")

    out_parts = [
        "# Paper Tables (auto-generated)",
        "",
        "본 문서는 `pipeline/build_tables.py` 가 누적된 result.json 들을 읽어 자동 생성합니다.",
        "",
        table1(args.bench_root),
        table2(runs_by_model),
        table3(runs_by_model),
        table4(runs_by_model),
        table5(args.aidev_eval),
        table6(runs_by_model),
    ]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(out_parts))
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()

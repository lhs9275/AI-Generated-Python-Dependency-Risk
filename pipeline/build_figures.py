"""
Paper Figure 자동 생성 (Phase 2).

Figure 1: RQ3 — Block-condition gradient (B0→B1→B2→B3) per model
Figure 2: RQ2 — G0 vs G1 SafetyPass-Core interaction per model
Figure 3: RQ1 — Risk-family × model heatmap (RiskyAcc at B0)

출력: research_notes/figures/fig{1,2,3}.pdf  (IEEE 인쇄용 grayscale-safe)
      research_notes/figures/fig{1,2,3}.png  (draft용 컬러)

사용법:
    python pipeline/build_figures.py [--results-dir results/]
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── 공통 설정 ─────────────────────────────────────────────────────────────────

MODEL_DISPLAY = {
    "Qwen2.5-Coder-7B-Instruct": "Qwen-7B",
    "Qwen2.5-Coder-14B-Instruct-AWQ": "Qwen-14B",
    "Qwen2.5-Coder-32B-Instruct-AWQ": "Qwen-32B",
    "deepseek-coder-6.7b-instruct": "DeepSeek-6.7B",
    "CodeLlama-7b-Instruct-hf": "CodeLlama-7B",
}
MODEL_ORDER = list(MODEL_DISPLAY.values())

FAMILY_LABELS = {
    "F1": "F1\nExistence",
    "F2": "F2\nVersion",
    "F3": "F3\nDirect\nVuln",
    "F4": "F4\nLicense",
    "F5": "F5\nTransitive\nVuln",
    "F6": "F6\nUnnec.\nDep",
}

# grayscale-safe: 흑백 인쇄도 구분 가능한 패턴 + 컬러
GRAY_HATCHES = ["", "///", "...", "xxx", "---"]
GRAY_COLORS  = ["#1a1a1a", "#555555", "#888888", "#aaaaaa", "#cccccc"]
COLOR_COLORS = ["#2166ac", "#4dac26", "#d7191c", "#f4a582", "#abd9e9"]

# IEEE single-column width ≈ 3.5in, double-column ≈ 7.2in
COL1 = 3.5
COL2 = 7.2

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "figure.dpi": 200,
    "pdf.fonttype": 42,   # embed fonts
    "ps.fonttype": 42,
})


# ── 데이터 로딩 (build_tables.py 와 동일 방식) ─────────────────────────────

def collect_runs(results_dir: Path, model_slug: str) -> list[dict]:
    try:
        from .config import is_canonical_run
    except ImportError:
        import re as _re
        _C = _re.compile(r"_G[01]_[0-9a-fA-F]+$")
        is_canonical_run = lambda n: bool(_C.search(n))
    by_key: dict = {}
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
        key = (r["task_id"], r.get("generation_condition", ""))
        if key not in by_key or p.stat().st_mtime > by_key[key].get("_mtime", 0):
            r["_mtime"] = p.stat().st_mtime
            by_key[key] = r
    return list(by_key.values())


def _val(run: dict, mode: str, dotpath: str) -> float | None:
    m = run.get("metrics_by_mode", {}).get(mode)
    if not m:
        return None
    obj = m
    for k in dotpath.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(k)
    return float(obj) if obj is not None else None


def mode_rate(runs: list[dict], mode: str, key: str) -> tuple[float, int]:
    vals = [_val(r, mode, key) for r in runs]
    vals = [v for v in vals if v is not None]
    return sum(vals), len(vals)


# ── Figure 1: Block-condition gradient ────────────────────────────────────────

def fig1_gradient(runs_by_model: dict, out_dir: Path) -> None:
    """
    Grouped bar chart: RiskyAcc at B0/B1_det/B2_det/B3 for each model.
    Shows the reduction gradient from no-guard to full guard.
    """
    modes = ["B0", "B1_deterministic", "B2_deterministic", "B3"]
    mode_labels = ["B0\n(no guard)", "B1\n(vuln scan)", "B2\n(+license)", "B3\n(AgentSupplyGuard)"]

    data: dict[str, list[float]] = {m: [] for m in MODEL_ORDER}
    for slug, label in MODEL_DISPLAY.items():
        runs = runs_by_model.get(slug, [])
        for mode in modes:
            n_risky, total = mode_rate(runs, mode, "accepted.risky_accepted_patch")
            if total:
                data[label].append(100.0 * n_risky / total)
            else:
                data[label].append(0.0)

    fig, ax = plt.subplots(figsize=(COL2, 2.6))

    n_groups = len(modes)
    n_models = len(MODEL_ORDER)
    bar_w = 0.14
    x = np.arange(n_groups)

    for i, label in enumerate(MODEL_ORDER):
        offset = (i - n_models / 2 + 0.5) * bar_w
        vals = data[label]
        bars = ax.bar(x + offset, vals, bar_w,
                      color=COLOR_COLORS[i], hatch=GRAY_HATCHES[i],
                      edgecolor="black", linewidth=0.5, label=label)
        for bar, v in zip(bars, vals):
            if v > 1:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                        f"{v:.1f}", ha="center", va="bottom", fontsize=5.5, rotation=90)

    ax.set_xticks(x)
    ax.set_xticklabels(mode_labels, ha="center")
    ax.set_ylabel("Risky-Accepted-Patch Rate (%)")
    ax.set_ylim(0, 42)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.legend(ncol=5, loc="upper right", framealpha=0.9,
              bbox_to_anchor=(1.0, 1.0))
    ax.set_title("Figure 1. RQ3: Block-Condition Gradient (all five models, n=240 each)")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    fig.tight_layout()
    _save(fig, out_dir, "fig1_gradient")
    plt.close(fig)
    print("fig1_gradient saved")


# ── Figure 2: G0 vs G1 interaction ────────────────────────────────────────────

def fig2_grounding(runs_by_model: dict, out_dir: Path) -> None:
    """
    Paired bar chart: SafetyPass-Core (B3) for G0 vs G1, per model.
    Annotates the delta to show H2a (help) and H2b (backfire).
    """
    conds = ["G0", "G1"]
    sp_by_model: dict[str, dict[str, float]] = {}

    for slug, label in MODEL_DISPLAY.items():
        runs = runs_by_model.get(slug, [])
        sp_by_model[label] = {}
        for cond in conds:
            cond_runs = [r for r in runs if r.get("generation_condition") == cond]
            n, total = mode_rate(cond_runs, "B3", "generated.safety_pass_core")
            sp_by_model[label][cond] = 100.0 * n / total if total else 0.0

    fig, ax = plt.subplots(figsize=(COL2, 2.6))

    n_models = len(MODEL_ORDER)
    bar_w = 0.32
    x = np.arange(n_models)
    G0_color = "#4d9de0"
    G1_color = "#e15554"
    G0_hatch = ""
    G1_hatch = "///"

    g0_vals = [sp_by_model[m]["G0"] for m in MODEL_ORDER]
    g1_vals = [sp_by_model[m]["G1"] for m in MODEL_ORDER]

    ax.bar(x - bar_w / 2, g0_vals, bar_w,
           color=G0_color, hatch=G0_hatch, edgecolor="black", linewidth=0.5, label="G0 (ungrounded)")
    ax.bar(x + bar_w / 2, g1_vals, bar_w,
           color=G1_color, hatch=G1_hatch, edgecolor="black", linewidth=0.5, label="G1 (evidence-grounded)")

    # delta annotation
    for i, (m, g0, g1) in enumerate(zip(MODEL_ORDER, g0_vals, g1_vals)):
        delta = g1 - g0
        sign = "+" if delta >= 0 else ""
        color = "#2ca02c" if delta > 1 else ("#d62728" if delta < -1 else "#7f7f7f")
        y_pos = max(g0, g1) + 1.5
        ax.annotate(f"{sign}{delta:.1f}pp",
                    xy=(i, y_pos), ha="center", fontsize=6.5,
                    color=color, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(MODEL_ORDER, rotation=10, ha="right")
    ax.set_ylabel("SafetyPass-Core at B3 (%)")
    ax.set_ylim(0, 105)
    ax.axhline(0, color="black", linewidth=0.5)
    ax.legend(loc="lower right")
    ax.set_title("Figure 2. RQ2: Evidence-Grounded Generation (G0 vs G1) per Model")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    fig.tight_layout()
    _save(fig, out_dir, "fig2_grounding")
    plt.close(fig)
    print("fig2_grounding saved")


# ── Figure 3: Risk-family × model heatmap ─────────────────────────────────────

def fig3_heatmap(runs_by_model: dict, out_dir: Path) -> None:
    """
    Heatmap: rows=family, cols=model; cell=RiskyAcc at B0 (%).
    Grayscale + annotated values.
    """
    families = ["F1", "F2", "F3", "F4", "F5", "F6"]

    matrix = np.zeros((len(families), len(MODEL_ORDER)))
    for j, (slug, label) in enumerate(MODEL_DISPLAY.items()):
        runs = runs_by_model.get(slug, [])
        for i, fam in enumerate(families):
            fam_runs = [r for r in runs if r.get("task_id", "").startswith(f"task_{fam}_")]
            n, total = mode_rate(fam_runs, "B0", "accepted.risky_accepted_patch")
            matrix[i, j] = 100.0 * n / total if total else 0.0

    fig, ax = plt.subplots(figsize=(COL2, 2.8))

    im = ax.imshow(matrix, cmap="YlOrRd", aspect="auto", vmin=0, vmax=55)

    ax.set_xticks(range(len(MODEL_ORDER)))
    ax.set_xticklabels(MODEL_ORDER, rotation=15, ha="right")
    ax.set_yticks(range(len(families)))
    ax.set_yticklabels([FAMILY_LABELS[f] for f in families], fontsize=7)

    # cell annotations
    for i in range(len(families)):
        for j in range(len(MODEL_ORDER)):
            v = matrix[i, j]
            color = "white" if v > 35 else "black"
            ax.text(j, i, f"{v:.0f}%", ha="center", va="center",
                    fontsize=7, color=color, fontweight="bold")

    cbar = fig.colorbar(im, ax=ax, shrink=0.85, pad=0.02)
    cbar.set_label("RiskyAcc at B0 (%)", fontsize=7)
    cbar.ax.tick_params(labelsize=6)

    ax.set_title("Figure 3. RQ1: Risky-Accepted-Patch Rate by Risk Family and Model (B0, no guard)")

    fig.tight_layout()
    _save(fig, out_dir, "fig3_heatmap")
    plt.close(fig)
    print("fig3_heatmap saved")


# ── Figure 4 (bonus): AIDev external validation ───────────────────────────────

def fig4_aidev(out_dir: Path) -> None:
    """
    Stacked bar: per-agent AIDev primary risk vs evidence-gap vs true-negative.
    """
    agents = ["aider", "codex", "cursor", "continue", "devin", "claude-code"]
    totals = [8, 24, 8, 8, 12, 1]
    primary = [2, 10, 3, 2, 6, 0]
    gap_only = [4, 14, 4, 3, 4, 1]

    true_neg = [t - p - g for t, p, g in zip(totals, primary, gap_only)]

    fig, ax = plt.subplots(figsize=(COL1 + 0.5, 2.4))

    x = np.arange(len(agents))
    w = 0.55
    b1 = ax.bar(x, primary, w, color="#d62728", hatch="", edgecolor="black",
                linewidth=0.5, label="Primary risk (S1+S3)")
    b2 = ax.bar(x, gap_only, w, bottom=primary, color="#aec7e8", hatch="///",
                edgecolor="black", linewidth=0.5, label="Evidence-gap only (S5)")
    b3 = ax.bar(x, true_neg, w, bottom=[p+g for p,g in zip(primary,gap_only)],
                color="#e8e8e8", hatch="", edgecolor="black",
                linewidth=0.5, label="True negative")

    # rate labels on primary bars
    for i, (p, t) in enumerate(zip(primary, totals)):
        if p > 0:
            ax.text(i, p / 2, f"{100*p//t}%", ha="center", va="center",
                    fontsize=6, color="white", fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(agents, rotation=15, ha="right")
    ax.set_ylabel("Number of PRs")
    ax.set_ylim(0, 28)
    ax.legend(loc="upper right", fontsize=6)
    ax.set_title("Figure 4. AIDev External Validation\n(61 PRs, 6 agents)")
    ax.yaxis.grid(True, linestyle="--", alpha=0.4)
    ax.set_axisbelow(True)

    fig.tight_layout()
    _save(fig, out_dir, "fig4_aidev")
    plt.close(fig)
    print("fig4_aidev saved")


# ── 저장 헬퍼 ─────────────────────────────────────────────────────────────────

def _save(fig, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(out_dir / f"{name}.png", bbox_inches="tight", dpi=150)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", type=Path, default=Path("results"))
    ap.add_argument("--out-dir", type=Path, default=Path("research_notes/figures"))
    args = ap.parse_args()

    print("결과 데이터 로딩 중...")
    runs_by_model: dict[str, list[dict]] = {}
    for slug in MODEL_DISPLAY:
        runs = collect_runs(args.results_dir, slug)
        if runs:
            runs_by_model[slug] = runs
            print(f"  {MODEL_DISPLAY[slug]}: {len(runs)} runs")

    print("\nFigure 생성 중...")
    fig1_gradient(runs_by_model, args.out_dir)
    fig2_grounding(runs_by_model, args.out_dir)
    fig3_heatmap(runs_by_model, args.out_dir)
    fig4_aidev(args.out_dir)

    print(f"\n완료: {args.out_dir}/")
    for f in sorted(args.out_dir.glob("fig*.pdf")):
        print(f"  {f.name}")


if __name__ == "__main__":
    main()

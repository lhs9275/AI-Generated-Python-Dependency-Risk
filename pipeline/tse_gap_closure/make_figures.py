"""Two naturalistic-validation figures (matplotlib, Agg -> PDF).

fig_naturalistic_flow.pdf      data funnel: screened -> included -> changes -> primary risks
fig_gate_effect_naturalistic.pdf  per-variant primary-risky acceptance vs. safe-block rate
"""

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PRETTY = {
    "B0_no_gate": "B0", "B1_scanner_fail_open": "B1\nscan",
    "B1b_scanner_fail_closed": "B1b\nscan(fc)", "S1_existence": "S1",
    "S1S2_version": "S1+S2", "S1S2S3_direct_evidence": "S1+S2\n+S3",
    "S1S2S3_plus_license": "+lic", "B3_full_guard": "B3",
}
ORDER = list(PRETTY)


def _load(p):
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def fig_flow(adir, data, meta, log, agree, out):
    pd = agree["final_primary_dist"]
    stages = [
        ("Screened AI PRs", log["n_pr_pool"]),
        ("Dependency-changing", log["n_included_prs"]),
        ("Labelable dep. changes", agree["n_changes"]),
        ("Analysis pop. (add/chg)", meta["n_analysis_population_add_or_versionchange"]),
        ("Primary-risky (P1/P2/P3)", meta["n_primary_risky"]),
    ]
    labels = [s[0] for s in stages]
    vals = [s[1] for s in stages]
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    y = range(len(stages))
    ax.barh(list(y), vals, color="#3b6ea5", height=0.62)
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xscale("log")
    ax.set_xlabel("count (log scale)", fontsize=9)
    for i, v in enumerate(vals):
        ax.text(v * 1.05, i, str(v), va="center", fontsize=8)
    sub = (f"P1={pd.get('P1_NONEXISTENT_PACKAGE',0)}  "
           f"P2={pd.get('P2_INVALID_VERSION_SPEC',0)}  "
           f"P3={pd.get('P3_DIRECT_KNOWN_VULNERABILITY',0)}")
    ax.set_title("Naturalistic corpus funnel  (" + sub + ")", fontsize=9)
    ax.margins(x=0.18)
    fig.tight_layout()
    fig.savefig(out / "fig_naturalistic_flow.pdf")
    plt.close(fig)


def fig_gate(adir, out):
    rows = {r["variant"]: r for r in _load(adir / "naturalistic_validation_summary.csv")}
    xs, acc, sb = [], [], []
    for v in ORDER:
        r = rows.get(v)
        if not r:
            continue
        xs.append(PRETTY[v])
        acc.append(100 * float(r["primary_risky_acceptance_rate"]) if r["primary_risky_acceptance_rate"] else 0.0)
        sb.append(100 * float(r["safe_block_rate"]) if r["safe_block_rate"] else 0.0)
    fig, ax1 = plt.subplots(figsize=(6.6, 3.2))
    x = range(len(xs))
    l1 = ax1.plot(list(x), acc, "-o", color="#c0392b", label="primary-risky acceptance")
    ax1.set_ylabel("primary-risky acceptance (%)", color="#c0392b", fontsize=9)
    ax1.tick_params(axis="y", labelcolor="#c0392b")
    ax1.set_ylim(-3, 105)
    ax2 = ax1.twinx()
    l2 = ax2.plot(list(x), sb, "--s", color="#2c7fb8", label="safe-block (false positive)")
    ax2.set_ylabel("safe-block rate (%)", color="#2c7fb8", fontsize=9)
    ax2.tick_params(axis="y", labelcolor="#2c7fb8")
    ax2.set_ylim(-0.2, max(5, max(sb) * 1.3) if sb else 5)
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(xs, fontsize=8)
    ax1.set_title("Gate ladder on naturalistic AI dependency PRs", fontsize=10)
    lns = l1 + l2
    ax1.legend(lns, [l.get_label() for l in lns], fontsize=8, loc="center right")
    ax1.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out / "fig_gate_effect_naturalistic.pdf")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--analysis", default="outputs/tse_gap_closure/analysis")
    ap.add_argument("--data", default="outputs/tse_gap_closure/data")
    ap.add_argument("--out", default="outputs/tse_gap_closure/figures")
    args = ap.parse_args()
    adir, data, out = Path(args.analysis), Path(args.data), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((adir / "paired_stats.json").read_text())
    log = json.loads((data / "collection_log.json").read_text())
    agree = json.loads((data / "labeling_agreement.json").read_text())
    fig_flow(adir, data, meta, log, agree, out)
    fig_gate(adir, out)
    print(f"wrote 2 figures -> {out}")


if __name__ == "__main__":
    main()

"""
Workstream H — single-command export of all manuscript-facing RQ tables.

    python -m pipeline.analysis.export_manuscript_tables

Writes results/tables/table_rq{1..5}_*.csv, a markdown mirror of each, a
CHANGELOG entry recording any value changes vs the previously-exported tables
(no silent overwrite), and runs consistency checks tying RQ3/RQ4 numbers back to
the validated source files. Exits non-zero if a consistency check fails.

Table → corpus role (docs/protocols/corpus_interpretation_rules.md):
  RQ1 real-world PR        routine = precision/prevalence-bound; risk-pos = recall
  RQ2 agentic baseline     2026 agentic relevance + residual risk
  RQ3 gate effect          controlled paired intervention (internal validity)
  RQ4 ablation minimal gate which stages drive the effect; S1+S2+S3 ≈ B3
  RQ5 repair               R0/R1/R2 functional/safety tradeoff
"""
import csv
import json
import sys
from pathlib import Path

from pipeline.analysis.compute_real_pr_metrics import build_rq1
from pipeline.analysis.compute_agentic_metrics import build_rq2
from pipeline.analysis.compute_hybrid_study_tables import (
    build_rq3, build_rq4, build_rq5, _runs_by_model, _strict_rq3_metrics,
)

OUT_DIR = Path("results/tables")
CHANGELOG = OUT_DIR / "CHANGELOG.md"

# Manuscript ablation ΔS2 (pp), from pipeline/reproduce_tables.py MANUSCRIPT_ABLATION.
MANUSCRIPT_DELTA_S2 = {
    "Qwen-7B": 10.0, "Qwen-14B": 12.9, "Qwen-32B": 9.2,
    "DeepSeek-6.7B": 4.6, "CodeLlama-7B": 5.4,
}

TABLES = [
    ("table_rq1_real_world_pr", build_rq1),
    ("table_rq2_agentic_baseline", build_rq2),
    ("table_rq3_gate_effect", build_rq3),
    ("table_rq4_ablation_minimal_gate", build_rq4),
    ("table_rq5_repair", build_rq5),
]

RQ5_PRE_STRICT_NOTICE = (
    "This is a pre-strict-offline auxiliary repair sub-study; the authoritative "
    "strict AFSP is Table IV / `results/metrics_v2/table5_baseline_ladder_v2.csv`."
)


def _read_existing(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def _diff_rows(old: list[dict], new: list[dict]) -> list[str]:
    """Human-readable per-cell changes between old and new table versions."""
    changes = []
    if not old:
        changes.append(f"  + new table ({len(new)} rows)")
        return changes
    okeys = [r.get(list(r.keys())[0]) for r in old] if old else []
    nkeys = [r.get(list(r.keys())[0]) for r in new] if new else []
    if okeys != nkeys:
        changes.append(f"  ! row set changed (old {len(old)} → new {len(new)} rows)")
    old_by = {tuple(r.values())[0]: r for r in old}
    for nr in new:
        rid = tuple(nr.values())[0]
        orr = old_by.get(rid)
        if not orr:
            changes.append(f"  + added row: {rid}")
            continue
        for k, v in nr.items():
            ov = orr.get(k)
            if ov is not None and str(ov) != str(v):
                changes.append(f"  ~ {rid}.{k}: {ov} → {v}")
    return changes or ["  (no value changes)"]


def _write_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    cols = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_md(path: Path, rows: list[dict], title: str):
    if not rows:
        return
    cols = list(rows[0].keys())
    lines = [f"## {title}\n"]
    if title == "table_rq5_repair":
        lines.append(f"> Notice: {RQ5_PRE_STRICT_NOTICE}\n")
    lines += ["| " + " | ".join(cols) + " |",
             "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    path.write_text("\n".join(lines) + "\n")


def consistency_checks(rq3, rq4) -> list[str]:
    """Tie RQ3/RQ4 numbers back to the validated source files. Returns failures."""
    fails = []
    strict_runs = _runs_by_model()
    # RQ3 B0/B3/minimal-gate RiskyAcc and AFSP must equal strict canonical runs.
    for row in rq3:
        m = row["model"]
        src = _strict_rq3_metrics(strict_runs.get(m, []))
        for col in ("RiskyAcc_B0", "RiskyAcc_B3", "RiskyAcc_S1S2S3", "AFSP"):
            expected = src[col]
            if expected is not None and abs(float(row[col]) - expected) > 0.00005:
                fails.append(f"RQ3 {m} {col}: table={row[col]} vs canonical_runs={expected}")
    # RQ3 odds ratio must be >1 and McNemar p tiny (intervention reduces risk).
    for row in rq3:
        if row["McNemar_p_B0_vs_B3"] > 0.001:
            fails.append(f"RQ3 {row['model']}: B0-vs-B3 McNemar p={row['McNemar_p_B0_vs_B3']} not significant")
    # RQ4 ablation ΔS2 must match the manuscript value (PR-08 recompute).
    for row in rq4:
        exp = MANUSCRIPT_DELTA_S2.get(row["model"])
        got = row["ablation_delta_no_S2_pp"]
        if exp is not None and got is not None and abs(float(got) - exp) > 0.05:
            fails.append(f"RQ4 {row['model']} ΔS2: table={got} vs manuscript={exp}")
    # RQ4 minimal gate must be statistically indistinguishable from B3 (p > 0.05).
    for row in rq4:
        if row["McNemar_p_S1S2S3_vs_B3"] <= 0.05:
            fails.append(f"RQ4 {row['model']}: S1S2S3-vs-B3 p={row['McNemar_p_S1S2S3_vs_B3']} "
                         f"(minimal gate unexpectedly differs from full B3)")
    return fails


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    built = {}
    changelog_lines = ["# RQ table export changelog\n",
                       "(timestamp added by the wrapping commit / CI, not in-script "
                       "to keep output deterministic)\n"]

    for name, fn in TABLES:
        rows = fn()
        built[name] = rows
        csv_path = OUT_DIR / f"{name}.csv"
        old = _read_existing(csv_path)
        changelog_lines.append(f"\n## {name}")
        changelog_lines += _diff_rows(old, rows)
        _write_csv(csv_path, rows)
        _write_md(OUT_DIR / f"{name}.md", rows, name)
        print(f"  Wrote {len(rows)} rows → {csv_path}")

    fails = consistency_checks(built["table_rq3_gate_effect"],
                               built["table_rq4_ablation_minimal_gate"])
    changelog_lines.append("\n## consistency_checks")
    if fails:
        changelog_lines += [f"  FAIL: {x}" for x in fails]
    else:
        changelog_lines.append("  PASS: all RQ3/RQ4 numbers tie back to validated source files")

    CHANGELOG.write_text("\n".join(changelog_lines) + "\n")

    print("\n=== consistency checks ===")
    if fails:
        for x in fails:
            print(f"  FAIL: {x}")
        print(f"\n{len(fails)} consistency check(s) FAILED → see {CHANGELOG}")
        sys.exit(1)
    print("  PASS: all RQ3/RQ4 numbers tie back to validated source files")
    print(f"\nAll 5 RQ tables exported → {OUT_DIR}")


if __name__ == "__main__":
    main()

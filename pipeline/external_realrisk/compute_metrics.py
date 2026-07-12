"""Compute recall/precision/family/CI matrix + reviewer-facing artifacts.

Reads results/external_realrisk_py/evaluation.jsonl and writes the doc-spec output
set under results/external_realrisk_py/. Low results are reported as-is.
"""

import argparse
import csv
import json
from pathlib import Path

from pipeline.external_realrisk.metrics import compute_recall_matrix

CORPUS_ROLE = (
    "Risk-containing external recall stress-test. Positives are grounded in external "
    "authorities (OSV malicious-package advisories, OSV/GHSA vulnerability advisories, "
    "the PyPI release index) and labeled before any guard execution, independent of "
    "benchmark/risk_oracle.yaml. This is recall/precision evidence, NOT a prevalence "
    "estimate."
)

# Headline modes in ladder order for tables.
LADDER = ["B0", "B1_scanner", "S1_only", "S1_S2_S3", "B3"]


def _modes_in_order(matrix):
    present = list(matrix["modes"].keys())
    ordered = [m for m in LADDER if m in present]
    ordered += [m for m in present if m not in ordered]
    return ordered


def write_summary(matrix, rows, out_dir):
    fams_present = sorted({r["risk_family"] for r in rows if r["label"] == "risky"})
    summary = {
        "corpus_role": CORPUS_ROLE,
        "n_records": len(rows),
        "n_risky": sum(1 for r in rows if r["label"] == "risky"),
        "n_normal": sum(1 for r in rows if r["label"] == "normal"),
        "n_primary_risky": matrix["n_primary_risky"],
        "families_present": fams_present,
        "by_family": {f: sum(1 for r in rows if r["risk_family"] == f) for f in fams_present},
        "modes": matrix["modes"],
        "primary_note": "primary recall = S1/S2/S3 only; S5/F6 reported as secondary families.",
    }
    (out_dir / "summary_metrics.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))


def write_confusion(matrix, out_dir):
    with (out_dir / "confusion_matrix.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mode", "tp", "fn", "fp", "tn", "recall", "recall_ci_lo",
                    "recall_ci_hi", "precision", "false_block_rate", "negative_pass_rate"])
        for m in _modes_in_order(matrix):
            md = matrix["modes"][m]
            c = md["confusion"]
            lo, hi = md["recall_ci"]
            w.writerow([m, c["tp"], c["fn"], c["fp"], c["tn"], md["recall"], lo, hi,
                        md["precision"], md["false_block_rate"], md["negative_pass_rate"]])


def write_family_recall(matrix, out_dir):
    with (out_dir / "family_recall.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mode", "family", "n", "blocked", "recall"])
        for m in _modes_in_order(matrix):
            for fam, fr in matrix["modes"][m]["family_recall"].items():
                w.writerow([m, fam, fr["n"], fr["blocked"], fr["recall"]])


def write_false_block_cases(rows, out_dir):
    lines = ["# False-block cases (normals blocked, by mode)\n"]
    for m in LADDER:
        blocked = [r for r in rows if r["label"] == "normal" and r["decisions"].get(m) == "BLOCK"]
        if not any(m in r["decisions"] for r in rows):
            continue
        lines.append(f"\n## {m} — {len(blocked)} false block(s)\n")
        for r in blocked:
            lines.append(f"- `{r['package']}=={r.get('version')}` ({r['source_type']}) "
                         f"fired={r.get('fired_stages', {}).get(m)}")
    (out_dir / "false_block_cases.md").write_text("\n".join(lines) + "\n")


def write_failure_cases(rows, out_dir):
    lines = ["# Failure cases — risky records not blocked by B3\n",
             "Reported honestly; any miss is a finding, not hidden. A WARN means the "
             "risk WAS detected but fell below the blocking-severity policy threshold "
             "(surfaced to the developer, not gated); a PASS means undetected.\n"]
    warned = [r for r in rows if r["label"] == "risky" and r["decisions"].get("B3") == "WARN"]
    undetected = [r for r in rows if r["label"] == "risky" and r["decisions"].get("B3") == "PASS"]
    lines.append("\n## Detected-but-warned (sub-threshold severity)\n")
    if not warned:
        lines.append("- None.")
    for r in warned:
        lines.append(f"- [{r['risk_family']}] `{r['package']}=={r.get('version')}` "
                     f"({r['risk_label']}, {r.get('evidence_external_id')}) "
                     f"fired={r.get('fired_stages', {}).get('B3')}")
    lines.append("\n## Undetected (B3 PASS) — true misses\n")
    if not undetected:
        lines.append("- **None — B3 detected every risky record in this corpus.**")
    for r in undetected:
        lines.append(f"- [{r['risk_family']}] `{r['package']}=={r.get('version')}` "
                     f"({r['risk_label']}, {r.get('evidence_external_id')})")
    # also: risky records where S1_S2_S3 missed but B3 caught (full-guard added value)
    lines.append("\n## Risky caught by B3 but missed by S1+S2+S3 (full-guard added value)\n")
    extra = [r for r in rows if r["label"] == "risky"
             and r["decisions"].get("B3") == "BLOCK"
             and r["decisions"].get("S1_S2_S3") != "BLOCK"]
    if not extra:
        lines.append("- None: S1+S2+S3 core already catches everything B3 catches here.")
    for r in extra:
        lines.append(f"- [{r['risk_family']}] `{r['package']}` ({r['risk_label']})")
    (out_dir / "failure_cases.md").write_text("\n".join(lines) + "\n")


def write_repro_readme(out_dir):
    (out_dir / "reproducibility_README.md").write_text(
        "# External real-evidence recall corpus — reproduction\n\n"
        "```bash\n"
        "# 1. source the corpus (network: OSV export + PyPI/OSV per package)\n"
        "python3 -m pipeline.external_realrisk.source_records\n\n"
        "# 2. evaluate guard ladder + pip-audit baseline\n"
        "python3 -m pipeline.external_realrisk.run_matrix\n\n"
        "# 3. compute metrics + artifacts\n"
        "python3 -m pipeline.external_realrisk.compute_metrics\n"
        "```\n\n"
        f"{CORPUS_ROLE}\n\n"
        "Positives: S1 = OSV `MAL-` advisories (package 404 on PyPI); "
        "S3 = real GHSA/CVE advisories (vulnerable version in affected range); "
        "S2 = real package pinned to a version absent from the PyPI release index. "
        "Negatives = real routine-agent-PR dependency adds. Labels are fixed before "
        "guard execution.\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--eval", type=Path,
                    default=Path("results/external_realrisk_py/evaluation.jsonl"))
    ap.add_argument("--out-dir", type=Path,
                    default=Path("results/external_realrisk_py"))
    args = ap.parse_args()

    rows = [json.loads(l) for l in args.eval.read_text().splitlines() if l.strip()]
    # convert eval rows into the metrics row schema
    mrows = [{"record_id": r["record_id"], "label": r["label"],
              "family": r["risk_family"], "primary": r["primary"],
              "decisions": r["decisions"]} for r in rows]
    matrix = compute_recall_matrix(mrows)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_summary(matrix, rows, args.out_dir)
    write_confusion(matrix, args.out_dir)
    write_family_recall(matrix, args.out_dir)
    write_false_block_cases(rows, args.out_dir)
    write_failure_cases(rows, args.out_dir)
    write_repro_readme(args.out_dir)

    print(f"wrote artifacts to {args.out_dir}/")
    for m in _modes_in_order(matrix):
        md = matrix["modes"][m]
        print(f"  {m:24s} recall={md['recall']}  primary={md['primary_recall']}  "
              f"false_block={md['false_block_rate']}  precision={md['precision']}")


if __name__ == "__main__":
    main()

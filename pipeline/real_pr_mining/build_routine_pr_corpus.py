"""Build the routine real-PR dependency corpus from AIDev/GitHub PR records.

Reads one or more PR JSONL/JSON inputs (each PR carrying an embedded
``dep_changes`` list of {path, patch}), extracts manifest-aware dependency
changes, classifies PR types, de-duplicates, and writes:

  - data/real_pr_routine/pr_dependency_changes.csv   (one row per dep change)
  - data/real_pr_routine/pr_manifest.json            (per-PR manifest + pr_type)
  - results/real_pr/routine_pr_summary.json          (distribution summary)

This is the ROUTINE corpus: precision / prevalence-bound evidence only. It is
NOT used to estimate recall (see docs/protocols/corpus_interpretation_rules.md).
No prevalence claims are made here; this script is extraction infrastructure.
"""

import argparse
import ast
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.real_pr_mining.extract_dependency_changes import (  # noqa: E402
    extract_rows,
    pr_has_manifest_change,
)
from pipeline.real_pr_mining.classify_pr_type import classify_pr_type

CORPUS_ROLE = (
    "Routine-Agent-PR: precision / prevalence-bound evidence only. "
    "Not used to estimate recall unless independently labeled positive risks "
    "are present (see docs/protocols/corpus_interpretation_rules.md)."
)

# CSV column order (schema fields, minus schema_version which is constant).
CSV_FIELDS = [
    "pr_id", "pr_url", "repo_full_name", "agent_name", "is_agent_authored",
    "base_commit", "head_commit", "created_at", "merged_at", "ecosystem",
    "manifest_path", "manifest_type", "change_type", "package_name",
    "normalized_package_name", "specifier_raw", "version_pin",
    "is_new_dependency", "is_runtime_dependency", "is_optional_dependency",
    "is_dev_dependency", "line_added", "line_removed", "pr_type",
    "extraction_confidence",
]


def _dedupe_key(r):
    return (r.get("pr_id"), r.get("manifest_path"),
            r.get("normalized_package_name"), r.get("change_type"))


def dedupe_rows(rows):
    """Collapse rows identical on (pr_id, manifest_path, normalized name, change_type)."""
    seen = {}
    for r in rows:
        seen.setdefault(_dedupe_key(r), r)
    return list(seen.values())


def build_summary(rows, n_prs):
    """Distribution summary over dependency-change rows. No prevalence claim."""
    by_agent = Counter(r.get("agent_name") for r in rows)
    by_manifest = Counter(r.get("manifest_type") for r in rows)
    by_change = Counter(r.get("change_type") for r in rows)
    by_pr_type = Counter(r.get("pr_type") for r in rows if r.get("pr_type"))
    repos = {r.get("repo_full_name") for r in rows}
    runtime_changes = sum(
        1 for r in rows
        if r.get("is_runtime_dependency") and r.get("change_type") in ("add", "version_change")
    )
    return {
        "corpus_role": CORPUS_ROLE,
        "n_prs": n_prs,
        "n_dependency_changes": len(rows),
        "n_runtime_add_or_change": runtime_changes,
        "n_repos": len(repos),
        "by_agent": dict(by_agent),
        "by_manifest_type": dict(by_manifest),
        "by_change_type": dict(by_change),
        "by_pr_type": dict(by_pr_type),
    }


def _load_prs(path: Path):
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return []
    try:
        d = json.loads(txt)
        return d if isinstance(d, list) else [d]
    except json.JSONDecodeError:
        out = []
        for line in txt.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return out


def _pr_key(pr):
    return pr.get("html_url") or pr.get("pr_api_url")


def build_corpus(inputs):
    """Return (rows, pr_manifest) for the union of PRs across input files.

    Dedupe is by PR url first (a PR may appear in several sample files), then by
    dependency-change row.
    """
    prs = {}
    for path in inputs:
        for pr in _load_prs(Path(path)):
            prs.setdefault(_pr_key(pr), pr)

    all_rows = []
    pr_manifest = []
    for pr in prs.values():
        rows = extract_rows(pr)
        pr_type = classify_pr_type(rows, had_manifest_change=pr_has_manifest_change(pr))
        for r in rows:
            r["pr_type"] = pr_type
        all_rows.extend(rows)
        pr_manifest.append({
            "pr_id": rows[0]["pr_id"] if rows else _pr_key(pr),
            "pr_url": pr.get("html_url"),
            "repo_full_name": rows[0]["repo_full_name"] if rows else None,
            "agent_name": pr.get("agent"),
            "pr_type": pr_type,
            "manifest_paths": sorted({r["manifest_path"] for r in rows}),
            "n_changes": len(rows),
        })
    return dedupe_rows(all_rows), pr_manifest, len(prs)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", nargs="+", required=True,
                   help="PR JSONL/JSON files with embedded dep_changes.")
    p.add_argument("--out-csv", type=Path,
                   default=Path("data/real_pr_routine/pr_dependency_changes.csv"))
    p.add_argument("--out-manifest", type=Path,
                   default=Path("data/real_pr_routine/pr_manifest.json"))
    p.add_argument("--out-summary", type=Path,
                   default=Path("results/real_pr/routine_pr_summary.json"))
    args = p.parse_args()

    rows, pr_manifest, n_prs = build_corpus(args.input)
    summary = build_summary(rows, n_prs)

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    args.out_summary.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    args.out_manifest.write_text(
        json.dumps(pr_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    args.out_summary.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"PRs: {n_prs}  dependency-change rows: {len(rows)}  "
          f"runtime add/change: {summary['n_runtime_add_or_change']}")
    print(f"by manifest_type: {summary['by_manifest_type']}")
    print(f"by pr_type: {summary['by_pr_type']}")
    print(f"wrote {args.out_csv}, {args.out_manifest}, {args.out_summary}")


if __name__ == "__main__":
    main()

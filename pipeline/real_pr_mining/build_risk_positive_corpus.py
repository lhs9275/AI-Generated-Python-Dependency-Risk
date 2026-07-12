"""
Workstream D: risk-positive real-world PR corpus support.

Selects candidates from the Routine-Agent-PR historical evidence for
independent labeling as a recall/construct-validity corpus.

Three tiers:
  deterministic positive  — S1/S2(robust)/S3 with high confidence
  manual review           — S2-postdates_pr (premature pin), license_missing
  excluded               — no signal, low-confidence, or clean rows

THIS CORPUS IS NOT USED TO ESTIMATE PREVALENCE. It is a recall / construct-
validity corpus. See docs/protocols/corpus_interpretation_rules.md.
"""

import argparse
import csv
import json
from pathlib import Path

CORPUS_ROLE_WARNING = (
    "This corpus is not used to estimate prevalence. "
    "It is a recall / construct-validity corpus assembled from deterministic "
    "positive signals and manual-review candidates. "
    "See docs/protocols/corpus_interpretation_rules.md."
)

ANNOTATION_COLS = [
    "case_id",
    "pr_url",
    "repo_full_name",
    "manifest_path",
    "package_name",
    "version_specifier",
    "risk_family_candidate",
    "annotator_id",
    "label",
    "confidence",
    "evidence_url_or_snapshot_id",
    "rationale",
    "adjudicated_label",
    "adjudication_notes",
]

# Maps evidence signal to D.3 risk family string.
_SIGNAL_TO_FAMILY = {
    "S1": "S1_package_nonexistent",
    "S2_nonexistent": "S2_invalid_version",
    "S2_yanked": "S2_invalid_version",
    "S2_postdates": "S2_invalid_version",
    "S3": "S3_direct_advisory",
    "license": "S5_license_policy_violation",
}


def _make_case_id(ev, signal_key):
    pr = ev.get("pr_id", "")
    pkg = ev.get("normalized_package_name", "")
    ver = ev.get("version_pin") or "nopin"
    return f"{pr}::{pkg}::{ver}::{signal_key}"


def select_candidates(evidence_rows):
    """Select risk-positive candidates from evidence rows (Workstream C output).

    Returns a list of candidate dicts, one per (row, signal) pair.
    clean rows (no signal) are excluded.
    """
    seen_ids = set()
    candidates = []

    for ev in evidence_rows:
        s1 = ev.get("S1", False)
        s2 = ev.get("S2", False)
        s3 = ev.get("S3", False)
        absence = ev.get("s2_absence_kind")
        lic_missing = ev.get("license_missing", False)

        entries = []

        if s3:
            entries.append(("S3", "S3", "positive", "high"))
        if s1:
            entries.append(("S1", "S1", "positive", "high"))
        if s2:
            if absence == "postdates_pr":
                entries.append(("S2_postdates", "S2", "uncertain", "medium"))
            elif absence == "yanked":
                entries.append(("S2_yanked", "S2", "positive", "high"))
            elif absence == "nonexistent":
                entries.append(("S2_nonexistent", "S2", "positive", "high"))
            else:
                # S2 with unknown absence kind → uncertain
                entries.append(("S2_postdates", "S2", "uncertain", "medium"))
        if lic_missing and not (s1 or s2 or s3):
            entries.append(("license", "license", "uncertain", "medium"))

        for signal_key, _family_key, label, confidence in entries:
            family = _SIGNAL_TO_FAMILY[signal_key]
            case_id = _make_case_id(ev, signal_key)
            if case_id in seen_ids:
                continue
            seen_ids.add(case_id)

            cand = {
                "case_id": case_id,
                "pr_id": ev.get("pr_id", ""),
                "pr_url": ev.get("pr_url", ""),
                "repo_full_name": ev.get("repo_full_name", ""),
                "manifest_path": ev.get("manifest_path", ""),
                "package_name": ev.get("package_name", ""),
                "normalized_package_name": ev.get("normalized_package_name", ""),
                "version_specifier": ev.get("specifier_raw", "") or ev.get("version_pin", ""),
                "risk_family_candidate": family,
                "signal_key": signal_key,
                "label": label,
                "confidence": confidence,
                "evidence_ids": json.dumps(ev.get("direct_advisory_ids", []) or []),
                "pr_time": ev.get("pr_time", ""),
                "pr_time_basis": ev.get("pr_time_basis", ""),
                "s2_absence_kind": absence or "",
            }
            candidates.append(cand)

    return candidates


def make_annotation_row(candidate, annotator_id=""):
    """Build an annotation CSV row from a candidate dict (D.5 schema)."""
    advisory_ids = []
    try:
        advisory_ids = json.loads(candidate.get("evidence_ids", "[]") or "[]")
    except (json.JSONDecodeError, TypeError):
        pass

    evidence_ref = ""
    if advisory_ids:
        evidence_ref = "; ".join(advisory_ids)
    elif candidate.get("signal_key") in ("S2_postdates", "S2_yanked", "S2_nonexistent", "S1"):
        evidence_ref = f"pypi::{candidate.get('normalized_package_name', '')}::{candidate.get('version_specifier', '')}"
    elif candidate.get("signal_key") == "license":
        evidence_ref = f"pypi::{candidate.get('normalized_package_name', '')}::license_missing"

    return {
        "case_id": candidate["case_id"],
        "pr_url": candidate.get("pr_url", ""),
        "repo_full_name": candidate.get("repo_full_name", ""),
        "manifest_path": candidate.get("manifest_path", ""),
        "package_name": candidate.get("package_name", ""),
        "version_specifier": candidate.get("version_specifier", ""),
        "risk_family_candidate": candidate.get("risk_family_candidate", ""),
        "annotator_id": annotator_id,
        "label": candidate.get("label", ""),
        "confidence": candidate.get("confidence", ""),
        "evidence_url_or_snapshot_id": evidence_ref,
        "rationale": "",
        "adjudicated_label": "",
        "adjudication_notes": "",
    }


def build_summary(candidates, n_routine_changes, target=80):
    """Build risk_positive_summary.json content (D.6)."""
    from collections import Counter

    by_family = Counter(c["risk_family_candidate"] for c in candidates)
    by_label = Counter(c["label"] for c in candidates)

    n_det_positive = sum(1 for c in candidates if c["label"] == "positive")
    n_manual = sum(1 for c in candidates if c["label"] in ("uncertain", ""))
    n_total = len(candidates)

    gap = max(0, target - n_total)

    return {
        "corpus_role": CORPUS_ROLE_WARNING,
        "n_routine_changes_source": n_routine_changes,
        "n_candidates_total": n_total,
        "n_deterministic_positive": n_det_positive,
        "n_manual_review_needed": n_manual,
        "target_cases": target,
        "cases_found": n_total,
        "gap": gap,
        "gap_note": (
            f"Target of {target} cases not reached. Only {n_total} candidates "
            "extracted from the routine corpus. "
            "Additional risk-positive PRs would require a dedicated search "
            "(e.g. mining CVE-linked PRs, vulnerability-fix commits, or "
            "targeted GitHub search for known-risky packages)."
            if gap > 0 else ""
        ),
        "by_risk_family": dict(by_family),
        "by_label": dict(by_label),
        "deterministic_positive_breakdown": {
            "S1_package_nonexistent": sum(
                1 for c in candidates
                if c["risk_family_candidate"] == "S1_package_nonexistent"
                and c["label"] == "positive"
            ),
            "S2_invalid_version_robust": sum(
                1 for c in candidates
                if c["risk_family_candidate"] == "S2_invalid_version"
                and c["label"] == "positive"
                and c.get("s2_absence_kind") in ("nonexistent", "yanked")
            ),
            "S2_invalid_version_postdates": sum(
                1 for c in candidates
                if c["risk_family_candidate"] == "S2_invalid_version"
                and c.get("s2_absence_kind") == "postdates_pr"
            ),
            "S3_direct_advisory": sum(
                1 for c in candidates
                if c["risk_family_candidate"] == "S3_direct_advisory"
                and c["label"] == "positive"
            ),
        },
        "manual_only_families": ["S4_transitive_advisory", "S5_license_policy_violation", "S6_unnecessary_dependency"],
        "manual_annotation_status": "round1 template generated; not yet annotated",
        "irr_status": "pending — annotation not complete",
    }


def _write_csv(path, rows, fieldnames):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _enrich_evidence_row(ev, pr_meta=None):
    """Add derived S1/S2/S3, s2_absence_kind, version_pin, specifier_raw to evidence row.

    Evidence JSONL stores raw PyPI/OSV fields; this function applies the same
    derive_risk_labels / classify_version_absence logic used in
    reconstruct_historical_evidence so select_candidates can work uniformly.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pipeline.evidence.reconstruct_historical_evidence import (
        derive_risk_labels, classify_version_absence,
    )
    labels = derive_risk_labels(ev)
    ev.update(labels)  # S1, S2, S3, deterministic

    # S2 disaggregation
    ev["s2_absence_kind"] = classify_version_absence(ev) if ev.get("S2") else None

    # Normalise field names: evidence JSONL uses 'version', PR CSV uses 'version_pin'
    if "version_pin" not in ev:
        ev["version_pin"] = ev.get("version")

    # Merge metadata from PR CSV if provided (pr_url, manifest_path, specifier_raw)
    if pr_meta:
        for field in ("pr_url", "repo_full_name", "manifest_path", "specifier_raw"):
            if field not in ev or not ev[field]:
                ev[field] = pr_meta.get(field, "")

    return ev


def _build_pr_lookup(pr_changes_csv):
    """Index pr_dependency_changes.csv by (pr_id, normalized_package_name, version_pin).

    Used to enrich evidence rows with pr_url, manifest_path, specifier_raw.
    """
    lookup = {}
    try:
        with open(pr_changes_csv, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row["pr_id"], row["normalized_package_name"], row.get("version_pin", ""))
                if key not in lookup:
                    lookup[key] = row
    except FileNotFoundError:
        pass
    return lookup


def main():
    parser = argparse.ArgumentParser(description="Build risk-positive candidate corpus (Workstream D)")
    parser.add_argument("--evidence", default="data/real_pr_routine/historical_evidence.jsonl")
    parser.add_argument("--pr-changes", default="data/real_pr_routine/pr_dependency_changes.csv")
    parser.add_argument("--candidates-out", default="data/real_pr_risk_positive/candidates.csv")
    parser.add_argument("--labels-round1-out", default="evaluation/manual_audit/risk_positive_labels_round1.csv")
    parser.add_argument("--labels-adjudicated-out", default="evaluation/manual_audit/risk_positive_labels_adjudicated.csv")
    parser.add_argument("--summary-out", default="results/real_pr/risk_positive_summary.json")
    parser.add_argument("--target", type=int, default=80)
    args = parser.parse_args()

    pr_lookup = _build_pr_lookup(args.pr_changes)
    raw_rows = [json.loads(l) for l in open(args.evidence)]
    evidence_rows = []
    for ev in raw_rows:
        key = (ev.get("pr_id", ""), ev.get("normalized_package_name", ""),
               ev.get("version") or "")
        meta = pr_lookup.get(key)
        evidence_rows.append(_enrich_evidence_row(ev, meta))

    candidates = select_candidates(evidence_rows)

    candidate_cols = [
        "case_id", "pr_id", "pr_url", "repo_full_name", "manifest_path",
        "package_name", "normalized_package_name", "version_specifier",
        "risk_family_candidate", "signal_key", "label", "confidence",
        "evidence_ids", "pr_time", "pr_time_basis", "s2_absence_kind",
    ]
    _write_csv(args.candidates_out, candidates, candidate_cols)

    annotation_rows = [make_annotation_row(c, annotator_id="") for c in candidates]
    _write_csv(args.labels_round1_out, annotation_rows, ANNOTATION_COLS)
    _write_csv(args.labels_adjudicated_out, annotation_rows, ANNOTATION_COLS)

    summary = build_summary(candidates, len(evidence_rows), target=args.target)
    Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.summary_out, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Candidates: {len(candidates)}")
    print(f"  deterministic positive: {summary['n_deterministic_positive']}")
    print(f"  manual review: {summary['n_manual_review_needed']}")
    print(f"  target {args.target}, gap {summary['gap']}")
    print(f"Wrote: {args.candidates_out}")
    print(f"Wrote: {args.labels_round1_out}")
    print(f"Wrote: {args.labels_adjudicated_out}")
    print(f"Wrote: {args.summary_out}")


if __name__ == "__main__":
    main()

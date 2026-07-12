#!/usr/bin/env python3
"""labeler_A -- deterministic, evidence-based dependency-risk labeler.

This is the *deterministic evidence-based* labeler for the independent
dependency-risk labeling study. It assigns a guard-INDEPENDENT primary risk
label to each dependency change using ONLY public evidence reconstructed at
PR creation time (the `time_aligned_evidence.jsonl` corpus).

Independence guarantees (do NOT relax):
  * No code under pipeline/guard/, pipeline/tse_gap_closure/ (other than this
    file), or pipeline/external_realrisk/ is imported or consulted.
  * No guard output file is read.
  * All decision logic below is implemented from scratch; the only input is
    the time-aligned public-evidence corpus.

Labels are later compared (Cohen's kappa) against a second, independently
written labeler. The two labelers must not collude.

Primary label = the single most-severe rule that fires, else "NONE".
Only change_type in {add, version_change} can be risky; "remove" -> "NONE".

  P1_NONEXISTENT_PACKAGE      pypi_exists_at_pr_time is exactly False.
  P2_INVALID_VERSION_SPEC     non-empty exact pin AND valid_version_at_pr_time
                              is exactly False AND P1 does not apply.
  P3_DIRECT_KNOWN_VULNERABILITY
                              direct_advisory_known_at_pr_time is True AND
                              P1/P2 do not apply.
  NONE                        otherwise.

Secondary label (independent of primary; most-relevant, else "NONE"):
  S8_EVIDENCE_UNRESOLVED      time_alignment_quality == "unresolved".
  S7_METADATA_MISSING         only when justifiable from the visible fields.
  (S4/S5/S6 are out of this labeler's evidence scope -> NONE.)

Confidence:
  high    time_alignment_quality == "exact"
  medium  time_alignment_quality == "approximate"
  low     time_alignment_quality in {"current_only", "unresolved"} (or other)

Pure stdlib only (json, csv, argparse).
"""

import argparse
import csv
import json
from collections import Counter

DEFAULT_EVIDENCE = "outputs/tse_gap_closure/data/time_aligned_evidence.jsonl"
DEFAULT_OUT = "outputs/tse_gap_closure/data/labels_A.csv"

EVIDENCE_SOURCE = "time_aligned_evidence(labeler_A)"

CSV_COLUMNS = [
    "change_id",
    "pr_id",
    "repo",
    "created_at",
    "package_name",
    "pinned_version",
    "change_type",
    "label_primary",
    "label_secondary",
    "label_confidence",
    "evidence_source",
    "evidence_note",
]

RISKY_CHANGE_TYPES = {"add", "version_change"}


def _is_nonempty_pin(pinned_version):
    """True iff pinned_version is a non-empty exact pin string."""
    if pinned_version is None:
        return False
    if isinstance(pinned_version, str):
        return pinned_version.strip() != ""
    # Any non-string, non-None value counts as a present pin.
    return True


def decide_primary(change_type, pinned_version, evidence):
    """Return (label_primary, evidence_note) for one change.

    Most-severe-wins ordering: P1 > P2 > P3 > NONE. Only add/version_change
    can be risky.
    """
    if change_type not in RISKY_CHANGE_TYPES:
        return "NONE", "change_type=%s (not risky)" % change_type

    pypi_at_pr = evidence.get("pypi_exists_at_pr_time")
    valid_ver_at_pr = evidence.get("valid_version_at_pr_time")
    advisory_known = evidence.get("direct_advisory_known_at_pr_time")

    # P1 -- package absent on PyPI at PR creation time.
    # null (undeterminable) does NOT trigger P1; require exactly False.
    if pypi_at_pr is False:
        return "P1_NONEXISTENT_PACKAGE", "pypi_exists_at_pr_time=False"

    # P2 -- package existed but the exact pinned version did not.
    # Require a non-empty exact pin and valid_version_at_pr_time exactly False.
    if _is_nonempty_pin(pinned_version) and valid_ver_at_pr is False:
        return (
            "P2_INVALID_VERSION_SPEC",
            "valid_version_at_pr_time=False; pinned_version=%s" % pinned_version,
        )

    # P3 -- a direct advisory known at PR time covers the pinned version.
    # Advisories that appear only in post_pr_disclosed_advisory_ids do NOT count
    # (the evidence flag direct_advisory_known_at_pr_time already excludes them).
    if advisory_known is True:
        advisory_ids = evidence.get("advisory_ids") or []
        ids_str = ",".join(str(a) for a in advisory_ids) if advisory_ids else ""
        note = "direct_advisory_known_at_pr_time=True"
        if ids_str:
            note += "; advisory_ids=%s" % ids_str
        return "P3_DIRECT_KNOWN_VULNERABILITY", note

    return "NONE", "no PR-time risk evidence"


def decide_secondary(evidence):
    """Return (label_secondary, note_fragment) independent of the primary label."""
    taq = evidence.get("time_alignment_quality")

    # S8 -- cannot confirm the PR-time state at all.
    if taq == "unresolved":
        return "S8_EVIDENCE_UNRESOLVED", "time_alignment_quality=unresolved"

    # S7 -- package exists now but no resolvable license/metadata signal is
    # visible in the evidence. The corpus carries no license field, and the
    # only metadata anchor present is package_created_at. Only justify S7 when
    # the package exists now yet that anchor is also missing -- i.e. genuinely
    # no resolvable metadata signal. Otherwise leave NONE.
    exists_now = evidence.get("pypi_exists_now")
    package_created_at = evidence.get("package_created_at")
    if exists_now is True and not package_created_at:
        return "S7_METADATA_MISSING", "no resolvable package metadata signal"

    return "NONE", ""


def decide_confidence(evidence):
    """Map time_alignment_quality to a confidence bucket."""
    taq = evidence.get("time_alignment_quality")
    if taq == "exact":
        return "high"
    if taq == "approximate":
        return "medium"
    # "current_only", "unresolved", or anything else -> low.
    return "low"


def label_row(obj):
    """Produce one CSV row dict from one evidence object."""
    evidence = obj.get("evidence") or {}
    change_type = obj.get("change_type")
    pinned_version = obj.get("pinned_version")

    label_primary, primary_note = decide_primary(change_type, pinned_version, evidence)
    label_secondary, secondary_note = decide_secondary(evidence)
    label_confidence = decide_confidence(evidence)

    note = primary_note
    if secondary_note:
        note = "%s | %s" % (note, secondary_note)

    pv = pinned_version
    if pv is None:
        pv = ""

    return {
        "change_id": obj.get("change_id", ""),
        "pr_id": obj.get("pr_id", ""),
        "repo": obj.get("repo", ""),
        "created_at": obj.get("created_at", ""),
        "package_name": obj.get("package_name", ""),
        "pinned_version": pv,
        "change_type": change_type if change_type is not None else "",
        "label_primary": label_primary,
        "label_secondary": label_secondary,
        "label_confidence": label_confidence,
        "evidence_source": EVIDENCE_SOURCE,
        "evidence_note": note,
    }


def run(evidence_path, out_path):
    rows = []
    n_lines = 0
    with open(evidence_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n_lines += 1
            obj = json.loads(line)
            rows.append(label_row(obj))

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return n_lines, rows


def main():
    parser = argparse.ArgumentParser(
        description="labeler_A: deterministic evidence-based dependency-risk labeler "
        "(guard-independent)."
    )
    parser.add_argument(
        "--evidence",
        default=DEFAULT_EVIDENCE,
        help="Path to time-aligned evidence JSONL (default: %(default)s)",
    )
    parser.add_argument(
        "--out",
        default=DEFAULT_OUT,
        help="Output CSV path (default: %(default)s)",
    )
    args = parser.parse_args()

    n_lines, rows = run(args.evidence, args.out)

    primary_dist = Counter(r["label_primary"] for r in rows)
    secondary_dist = Counter(r["label_secondary"] for r in rows)

    print("labeler_A (deterministic evidence-based, guard-independent)")
    print("evidence : %s" % args.evidence)
    print("out      : %s" % args.out)
    print("evidence lines read : %d" % n_lines)
    print("csv rows written    : %d" % len(rows))
    print("label_primary distribution:")
    for label, count in primary_dist.most_common():
        print("  %-28s %d" % (label, count))
    print("label_secondary distribution:")
    for label, count in secondary_dist.most_common():
        print("  %-28s %d" % (label, count))


if __name__ == "__main__":
    main()

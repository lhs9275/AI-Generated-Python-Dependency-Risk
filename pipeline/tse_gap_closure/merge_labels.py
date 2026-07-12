"""Merge the two independent labelers, measure agreement, adjudicate, finalize.

Inputs: labels_A.csv (deterministic evidence-based) and labels_B.csv (independent
live PyPI/OSV re-query) -- written by two separate implementations that never saw
each other's code (command 4.5).

Outputs:
  independent_labels.csv  final per-change label in the command 4.2 schema
  adjudication_log.csv     every A/B disagreement + how it was resolved

Agreement: Cohen's kappa on the primary label (4 classes) and on the binary
risky/not split, reported separately from secondary (command 4.5). Disagreements
are adjudicated against the EXACT-timestamp evidence reconstruction
(time_aligned_evidence.jsonl) -- a documented, evidence-grounded referee applied
ONLY to the changes where A and B differ.
"""

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

from pipeline.stdlib_names import is_stdlib

PRIMARY = {"P1_NONEXISTENT_PACKAGE", "P2_INVALID_VERSION_SPEC", "P3_DIRECT_KNOWN_VULNERABILITY"}
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_NOT_A_PACKAGE = {"python", "pip", "sqlite3", "os", "sys", "json", "re", "venv"}


def implausible_reason(name):
    """Why a token is not a labelable PyPI distribution name (command 3.4 exclusion)."""
    if not name:
        return "empty_name"
    if not _NAME_RE.match(name):
        return "bad_chars"
    if is_stdlib(name) or name in _NOT_A_PACKAGE:
        return "stdlib_or_not_a_package"
    if name.isupper() and len(name) >= 3:
        return "allcaps_constant"   # HOST / PORT / MAX_ITERATIONS -> extraction noise
    return None


def grade_primary(label, ev):
    """Evidence strength sub-grade for a primary label (transparency, not filtering)."""
    e = (ev or {}).get("evidence", {})
    if label == "P1_NONEXISTENT_PACKAGE":
        # high: package created strictly after the PR (exists now, but not at PR time);
        # medium: 404 on PyPI now (hallucinated/removed/private -- cannot fully separate).
        return "high_created_after_pr" if e.get("pypi_exists_now") else "medium_404_now"
    if label == "P2_INVALID_VERSION_SPEC":
        # strong: version absent from PyPI even now (hallucinated/invalid pin);
        # conditional: version first released after the PR (invalid only at PR time).
        return "strong_absent_now" if not e.get("version_exists_now") else "conditional_released_after_pr"
    if label == "P3_DIRECT_KNOWN_VULNERABILITY":
        return "advisory_published_before_pr"
    return ""


def _load_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["change_id"]: r for r in csv.DictReader(fh)}


def _cohen_kappa(pairs):
    """Cohen's kappa for a list of (a_label, b_label) categorical pairs."""
    n = len(pairs)
    if n == 0:
        return None
    cats = sorted({x for p in pairs for x in p})
    po = sum(1 for a, b in pairs if a == b) / n
    a_marg = Counter(a for a, _ in pairs)
    b_marg = Counter(b for _, b in pairs)
    pe = sum((a_marg[c] / n) * (b_marg[c] / n) for c in cats)
    if pe == 1.0:
        return 1.0
    return round((po - pe) / (1 - pe), 4)


def _referee(ev_row):
    """Exact-timestamp adjudication of the primary label for one change."""
    if ev_row is None:
        return "NONE"
    ev = ev_row.get("evidence", {})
    ct = ev_row.get("change_type")
    if ct not in ("add", "version_change"):
        return "NONE"
    if ev.get("pypi_exists_at_pr_time") is False:
        return "P1_NONEXISTENT_PACKAGE"
    pinned = (ev_row.get("pinned_version") or "").strip()
    if pinned and ev.get("valid_version_at_pr_time") is False:
        return "P2_INVALID_VERSION_SPEC"
    if ev.get("direct_advisory_known_at_pr_time") is True:
        return "P3_DIRECT_KNOWN_VULNERABILITY"
    return "NONE"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", default="outputs/tse_gap_closure/data/labels_A.csv")
    ap.add_argument("--b", default="outputs/tse_gap_closure/data/labels_B.csv")
    ap.add_argument("--patches", default="outputs/tse_gap_closure/data/dependency_change_patches.jsonl")
    ap.add_argument("--evidence", default="outputs/tse_gap_closure/data/time_aligned_evidence.jsonl")
    ap.add_argument("--out", default="outputs/tse_gap_closure/data/independent_labels.csv")
    ap.add_argument("--adj", default="outputs/tse_gap_closure/data/adjudication_log.csv")
    ap.add_argument("--summary", default="outputs/tse_gap_closure/data/labeling_agreement.json")
    args = ap.parse_args()

    A = _load_csv(args.a)
    B = _load_csv(args.b)
    patches = {json.loads(l)["change_id"]: json.loads(l)
               for l in Path(args.patches).read_text().splitlines() if l.strip()}
    evidence = {json.loads(l)["change_id"]: json.loads(l)
                for l in Path(args.evidence).read_text().splitlines() if l.strip()}

    all_ids = [cid for cid in patches if cid in A and cid in B]
    # Command 3.4 exclusion: drop changes whose package token is not a labelable
    # PyPI distribution name (stdlib, config constants, parse artifacts).
    exclusions = []
    ids = []
    for cid in all_ids:
        why = implausible_reason(patches[cid].get("package_name"))
        if why:
            exclusions.append({"change_id": cid, "package_name": patches[cid].get("package_name"),
                               "change_type": patches[cid].get("change_type"), "exclude_reason": why})
        else:
            ids.append(cid)
    Path(args.adj).parent.mkdir(parents=True, exist_ok=True)
    with open(Path(args.adj).parent / "change_exclusions.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["change_id", "package_name", "change_type", "exclude_reason"])
        w.writeheader(); w.writerows(exclusions)

    # --- agreement (primary, binary-risky, secondary) ---
    prim_pairs = [(A[c]["label_primary"], B[c]["label_primary"]) for c in ids]
    bin_pairs = [("RISKY" if A[c]["label_primary"] in PRIMARY else "SAFE",
                  "RISKY" if B[c]["label_primary"] in PRIMARY else "SAFE") for c in ids]
    sec_pairs = [(A[c]["label_secondary"] or "NONE", B[c]["label_secondary"] or "NONE") for c in ids]
    agreement = {
        "n_changes": len(ids),
        "primary_kappa": _cohen_kappa(prim_pairs),
        "primary_agreement_rate": round(sum(1 for a, b in prim_pairs if a == b) / len(ids), 4),
        "binary_risky_kappa": _cohen_kappa(bin_pairs),
        "binary_risky_agreement_rate": round(sum(1 for a, b in bin_pairs if a == b) / len(ids), 4),
        "secondary_agreement_rate": round(sum(1 for a, b in sec_pairs if a == b) / len(ids), 4),
        "secondary_note": ("Labeler A's evidence scope did not include license/metadata; "
                           "S4/S7 secondary risks are contributed by labeler B's independent "
                           "re-query. Secondary agreement is therefore reported as a rate over "
                           "the shared scope only, not as a co-equal IRR; the rigorous IRR is "
                           "the primary-label kappa."),
        "labeler_A_primary_dist": dict(Counter(A[c]["label_primary"] for c in ids)),
        "labeler_B_primary_dist": dict(Counter(B[c]["label_primary"] for c in ids)),
    }

    # --- adjudicate disagreements + finalize ---
    final_rows, adj_rows = [], []
    for cid in ids:
        a, b = A[cid], B[cid]
        p = patches[cid]
        ev_row = evidence.get(cid)
        disagree = a["label_primary"] != b["label_primary"]
        if disagree:
            ref = _referee(ev_row)
            final_primary = ref
            adj_rows.append({
                "change_id": cid, "package_name": p.get("package_name"),
                "pinned_version": p.get("version_pin"), "created_at": p.get("created_at"),
                "labeler_A_primary": a["label_primary"], "labeler_B_primary": b["label_primary"],
                "adjudication_result": ref,
                "referee": "exact_timestamp_evidence",
                "referee_note": (a.get("evidence_note") or "") + " | " + (b.get("evidence_note") or ""),
            })
        else:
            final_primary = a["label_primary"]

        # final secondary: prefer the labeler that had scope to see it (B for license/meta),
        # else A's unresolved flag.
        final_secondary = b["label_secondary"] if b["label_secondary"] not in ("", "NONE") else \
            (a["label_secondary"] if a["label_secondary"] not in ("", "NONE") else "NONE")
        conf = "high" if (a["label_confidence"] == "high" or b["label_confidence"] == "high") else \
            (a["label_confidence"] or b["label_confidence"])

        final_rows.append({
            "pr_id": p.get("pr_id"), "repo": p.get("repo_full_name"),
            "pr_url": p.get("pr_url"), "created_at": p.get("created_at"),
            "merged_at": p.get("merged_at"),
            "tool_evidence": p.get("tool_evidence") or f"aidev_agent:{p.get('agent_name')}",
            "manifest_file": p.get("manifest_path"), "package_name": p.get("package_name"),
            "old_spec": "", "new_spec": p.get("specifier_raw") or "",
            "change_type": p.get("change_type"),
            "label_primary": final_primary, "label_secondary": final_secondary,
            "primary_grade": grade_primary(final_primary, ev_row),
            "label_confidence": conf,
            "evidence_source": "dual_independent(labeler_A=evidence; labeler_B=live_pypi_osv)",
            "evidence_timestamp": (ev_row or {}).get("evidence", {}).get("retrieved_at", ""),
            "labeler": "A+B", "adjudication_needed": disagree,
            "adjudication_result": (final_primary if disagree else ""),
            "change_id": cid,
            "notes": "",
        })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(final_rows[0].keys()))
        w.writeheader(); w.writerows(final_rows)
    with open(args.adj, "w", newline="", encoding="utf-8") as fh:
        if adj_rows:
            w = csv.DictWriter(fh, fieldnames=list(adj_rows[0].keys()))
            w.writeheader(); w.writerows(adj_rows)
        else:
            fh.write("change_id,package_name,pinned_version,created_at,labeler_A_primary,labeler_B_primary,adjudication_result,referee,referee_note\n")

    agreement["n_excluded_extraction_noise"] = len(exclusions)
    agreement["exclusion_reasons"] = dict(Counter(e["exclude_reason"] for e in exclusions))
    agreement["n_adjudicated"] = len(adj_rows)
    agreement["final_primary_dist"] = dict(Counter(r["label_primary"] for r in final_rows))
    agreement["final_secondary_dist"] = dict(Counter(r["label_secondary"] for r in final_rows))
    agreement["final_primary_grade_dist"] = dict(
        Counter(r["primary_grade"] for r in final_rows if r["label_primary"] in PRIMARY))
    Path(args.summary).write_text(json.dumps(agreement, indent=2, ensure_ascii=False))

    print(f"merged {len(ids)} labelable changes ({len(exclusions)} excluded as extraction noise: "
          f"{agreement['exclusion_reasons']})")
    print(f"  primary kappa = {agreement['primary_kappa']} "
          f"(agreement {agreement['primary_agreement_rate']:.3%})")
    print(f"  binary-risky kappa = {agreement['binary_risky_kappa']} "
          f"(agreement {agreement['binary_risky_agreement_rate']:.3%})")
    print(f"  adjudicated disagreements: {len(adj_rows)}")
    print(f"  final primary dist: {agreement['final_primary_dist']}")
    print(f"  final primary grade: {agreement['final_primary_grade_dist']}")
    print(f"  final secondary dist: {agreement['final_secondary_dist']}")


if __name__ == "__main__":
    main()

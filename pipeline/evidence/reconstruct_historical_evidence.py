"""Reconstruct PR-time public evidence for each routine-corpus dependency change.

For every row in data/real_pr_routine/pr_dependency_changes.csv, resolve the PR
time (C.4 priority), look up cached PyPI/OSV/license snapshots, and emit an
evidence row conforming to data/schema/evidence_snapshot.schema.json. Then derive
deterministic S1/S2/S3 label candidates, keeping low-confidence / live-only cases
separate (C.5/C.6), and write a coverage report.

The pure reasoning (resolve_pr_time, derive_risk_labels) is unit-tested with
frozen fixtures; the snapshot lookups are tested via cached JSON, never live.
"""

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.evidence import pypi_snapshot as P  # noqa: E402
from pipeline.evidence import osv_snapshot as O  # noqa: E402
from pipeline.evidence.license_snapshot import license_from_pypi  # noqa: E402

_TIME_PRIORITY = [("created_at", "high"), ("merged_at", "high"),
                  ("head_commit_time", "medium")]


def resolve_pr_time(row: dict, collection_time: str = None):
    """Return (timestamp, basis, timing_confidence) using the C.4 priority order."""
    for key, conf in _TIME_PRIORITY:
        if row.get(key):
            return row[key], key, conf
    return collection_time, "collection_time", "low"


def derive_risk_labels(ev: dict) -> dict:
    """Deterministic S1/S2/S3 positives, gated by confidence + provenance (C.5/C.6).

    A label is deterministic only when evidence_confidence is high, the PR-time
    basis is a real PR timestamp (not collection_time), and the evidence is not
    live-only.
    """
    conf = ev.get("evidence_confidence")
    basis = ev.get("pr_time_basis")
    src = ev.get("evidence_source")
    deterministic = (conf == "high"
                     and basis not in (None, "collection_time")
                     and src != "live_query")
    s1 = (ev.get("package_exists_at_pr_time") is False) and deterministic
    s2 = ((ev.get("version_exists_at_pr_time") is False
           or ev.get("version_yanked_at_pr_time") is True)
          and deterministic)
    s3 = bool(ev.get("direct_advisory_known_at_pr_time")) and deterministic
    return {"S1": s1, "S2": s2, "S3": s3, "deterministic": deterministic}


def _dt2(s):
    from datetime import datetime, timezone
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def classify_version_absence(ev: dict):
    """Disaggregate an S2 signal:

    - "yanked"        : version present but yanked at PR time
    - "nonexistent"   : version never uploaded (hallucination-grade invalid version)
    - "postdates_pr"  : version exists now but uploaded after the PR (premature pin;
                        sensitive to created_at accuracy, reported separately)
    - None            : version present and valid
    """
    if ev.get("version_yanked_at_pr_time") is True:
        return "yanked"
    if ev.get("version_exists_at_pr_time") is False:
        if not ev.get("version_upload_time"):
            return "nonexistent"
        return "postdates_pr"
    return None


def _confidence(timing_conf, package_exists, advisory_source_live):
    """Overall evidence_confidence from timing + lookup outcome."""
    if timing_conf == "low":
        return "low"
    if package_exists is None:
        return "low"
    if advisory_source_live:
        return "medium"
    return timing_conf  # high or medium


def build_evidence_row(row, pypi_json, osv_json, collected_at):
    """Assemble one evidence_snapshot row for a dependency-change row."""
    pr_time, basis, timing_conf = resolve_pr_time(row, collection_time=collected_at)
    name = row.get("normalized_package_name")
    version = row.get("version_pin")

    pkg_exists_now = bool(pypi_json) and bool(
        pypi_json.get("info") or pypi_json.get("releases"))
    facts = P.parse_pypi(pypi_json) if pypi_json else {"package_created_at": None,
                                                       "exists": False, "versions": {}}
    pkg_exists_at = P.package_exists_at(facts, pr_time) if pypi_json else (
        False if pypi_json is not None else None)
    # pypi_json is None -> 404 (package never existed) -> exists False/None handled below
    if pypi_json is None:
        pkg_exists_now = False
        pkg_exists_at = False  # a 404 today is weak; flagged low-confidence below
        timing_conf = "low" if basis == "collection_time" else timing_conf

    vfacts = (P.version_facts_at(facts, version, pr_time)
              if (pypi_json and version) else
              {"version_exists_at_pr_time": None, "version_upload_time": None,
               "version_yanked_at_pr_time": None})

    adv = (O.advisory_facts(osv_json, version, pr_time)
           if (osv_json and version) else
           {"direct_advisory_known_at_pr_time": None, "direct_advisory_ids": [],
            "advisory_published_at": None, "affected_range": None})
    advisory_source_live = bool(osv_json and version is None)

    spdx, lic_missing = license_from_pypi(pypi_json) if pypi_json else (None, True)

    src = "pypi" if pypi_json else ("live_query" if pypi_json is None else "cached_snapshot")
    if adv["direct_advisory_known_at_pr_time"]:
        src = "osv"
    conf = _confidence(timing_conf, pkg_exists_at, advisory_source_live)

    return {
        "schema_version": 1,
        "pr_id": row.get("pr_id"),
        "package_name": row.get("package_name"),
        "normalized_package_name": name,
        "version": version,
        "ecosystem": "pypi",
        "pr_time_basis": basis,
        "pr_time": pr_time,
        "package_exists_at_pr_time": pkg_exists_at,
        "package_created_at": facts.get("package_created_at"),
        "package_exists_now": pkg_exists_now,
        "version_exists_at_pr_time": vfacts["version_exists_at_pr_time"],
        "version_upload_time": vfacts["version_upload_time"],
        "version_yanked_at_pr_time": vfacts["version_yanked_at_pr_time"],
        "direct_advisory_known_at_pr_time": adv["direct_advisory_known_at_pr_time"],
        "direct_advisory_ids": adv["direct_advisory_ids"],
        "advisory_published_at": adv["advisory_published_at"],
        "affected_range": adv["affected_range"],
        "license_spdx_at_pr_time": spdx,
        "license_missing": lic_missing,
        "evidence_source": src,
        "evidence_collected_at": collected_at,
        "evidence_confidence": conf,
    }


def reconstruct(rows, cache_dir, collected_at, fetch=False, pause=0.0):
    """Build evidence rows for all dependency-change rows, using cached snapshots."""
    cache_dir = Path(cache_dir)
    pypi_dir, osv_dir = cache_dir / "pypi", cache_dir / "osv"
    names = sorted({r["normalized_package_name"] for r in rows})
    pypi_cache, osv_cache = {}, {}
    for i, name in enumerate(names):
        if fetch:
            pypi_cache[name] = P.fetch_pypi(name, pypi_dir, pause=pause)
            osv_cache[name] = O.fetch_osv(name, osv_dir, pause=pause)
        else:
            pj = pypi_dir / f"{name}.json"
            oj = osv_dir / f"{name}.json"
            pypi_cache[name] = json.loads(pj.read_text()) if pj.exists() else None
            osv_cache[name] = json.loads(oj.read_text()) if oj.exists() else {}

    evidence = []
    for r in rows:
        n = r["normalized_package_name"]
        evidence.append(build_evidence_row(r, pypi_cache.get(n), osv_cache.get(n), collected_at))
    return evidence


def coverage_report(evidence):
    """Coverage + deterministic S1/S2/S3 label candidates, split by confidence."""
    n = len(evidence)
    labels_hi = {"S1": [], "S2": [], "S3": []}
    labels_low = {"S1": [], "S2": [], "S3": []}
    s2_breakdown = Counter()  # nonexistent / postdates_pr / yanked among deterministic S2
    for ev in evidence:
        lab = derive_risk_labels(ev)
        key = f"{ev['pr_id']}::{ev['normalized_package_name']}::{ev.get('version')}"
        if lab["S2"]:
            s2_breakdown[classify_version_absence(ev) or "unknown"] += 1
        for s in ("S1", "S2", "S3"):
            if lab[s]:
                labels_hi[s].append(key)
            else:
                # candidate signal present but not deterministic (low conf / live / missing)
                raw = {
                    "S1": ev.get("package_exists_at_pr_time") is False,
                    "S2": (ev.get("version_exists_at_pr_time") is False
                           or ev.get("version_yanked_at_pr_time") is True),
                    "S3": bool(ev.get("direct_advisory_known_at_pr_time")),
                }
                if raw[s]:
                    labels_low[s].append(key)
    return {
        "corpus_role": ("Historical evidence for the Routine-Agent-PR corpus. "
                        "Deterministic S1/S2/S3 labels are precision/prevalence-bound; "
                        "low-confidence and live-only signals are reported separately "
                        "and excluded from prevalence (docs/protocols/"
                        "corpus_interpretation_rules.md)."),
        "n_dependency_changes": n,
        "n_with_version_pin": sum(1 for e in evidence if e.get("version")),
        "pr_time_basis": dict(Counter(e["pr_time_basis"] for e in evidence)),
        "evidence_confidence": dict(Counter(e["evidence_confidence"] for e in evidence)),
        "evidence_source": dict(Counter(e["evidence_source"] for e in evidence)),
        "package_exists_now": dict(Counter(e["package_exists_now"] for e in evidence)),
        "license_missing": sum(1 for e in evidence if e.get("license_missing")),
        "deterministic_positive_counts": {s: len(labels_hi[s]) for s in ("S1", "S2", "S3")},
        "low_confidence_candidate_counts": {s: len(labels_low[s]) for s in ("S1", "S2", "S3")},
        "s2_breakdown": dict(s2_breakdown),
        "s2_breakdown_note": ("S2 deterministic positives are disaggregated: "
                              "'nonexistent' = version never uploaded (hallucination-grade); "
                              "'postdates_pr' = version released after the PR (premature pin, "
                              "sensitive to created_at accuracy); 'yanked'. Only 'nonexistent' "
                              "and 'yanked' are robust invalid-version signals; 'postdates_pr' "
                              "needs manual review and is not a confident prevalence signal."),
        "deterministic_positives": labels_hi,
        "low_confidence_candidates": labels_low,
    }


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path,
                   default=Path("data/real_pr_routine/pr_dependency_changes.csv"))
    p.add_argument("--cache-dir", type=Path, default=Path("data/snapshots/cache"))
    p.add_argument("--snapshot-dir", type=Path, default=Path("data/snapshots"))
    p.add_argument("--out-coverage", type=Path,
                   default=Path("results/real_pr/historical_evidence_coverage.json"))
    p.add_argument("--out-evidence", type=Path,
                   default=Path("data/real_pr_routine/historical_evidence.jsonl"))
    p.add_argument("--fetch", action="store_true",
                   help="Fetch missing snapshots from PyPI/OSV (network); otherwise cache-only.")
    p.add_argument("--pause", type=float, default=0.1)
    args = p.parse_args()

    rows = list(csv.DictReader(args.input.open()))
    for r in rows:
        for k in list(r):
            if r[k] == "":
                r[k] = None

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    evidence = reconstruct(rows, args.cache_dir, collected_at,
                           fetch=args.fetch, pause=args.pause)
    report = coverage_report(evidence)

    _write_jsonl(args.out_evidence, evidence)
    # Snapshot tables (parquet engine unavailable in this env -> JSONL; see README).
    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(args.snapshot_dir / "pypi_releases.jsonl",
                 [{"name": e["normalized_package_name"],
                   "package_created_at": e["package_created_at"],
                   "package_exists_now": e["package_exists_now"]} for e in evidence])
    _write_jsonl(args.snapshot_dir / "osv_advisories.jsonl",
                 [{"name": e["normalized_package_name"], "version": e["version"],
                   "direct_advisory_ids": e["direct_advisory_ids"],
                   "known_at_pr_time": e["direct_advisory_known_at_pr_time"]}
                  for e in evidence if e["direct_advisory_ids"]])
    _write_jsonl(args.snapshot_dir / "license_metadata.jsonl",
                 [{"name": e["normalized_package_name"],
                   "license_spdx": e["license_spdx_at_pr_time"],
                   "license_missing": e["license_missing"]} for e in evidence])

    args.out_coverage.parent.mkdir(parents=True, exist_ok=True)
    args.out_coverage.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"evidence rows: {len(evidence)}")
    print(f"pr_time_basis: {report['pr_time_basis']}")
    print(f"evidence_confidence: {report['evidence_confidence']}")
    print(f"deterministic S1/S2/S3: {report['deterministic_positive_counts']}")
    print(f"low-confidence candidates: {report['low_confidence_candidate_counts']}")
    print(f"license_missing: {report['license_missing']}")


if __name__ == "__main__":
    main()

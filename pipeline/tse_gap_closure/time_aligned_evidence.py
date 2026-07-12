"""Reconstruct PR-time-aligned public evidence for each dependency change.

For every (package, pinned version, PR creation time) we recover, from the public
record as it stood AT PR TIME (command section 5):

  * package existence on PyPI at PR time (release upload time vs PR time),
  * validity of the pinned version at PR time,
  * direct OSV/GHSA advisories KNOWN at PR time (published <= PR time) that cover
    the pinned version -- advisories disclosed *after* the PR are recorded
    separately as ``post_pr_disclosed`` and never counted as a PR-time risk.

All PyPI/OSV responses are fetched through the cached snapshot helpers
(``pipeline.evidence.pypi_snapshot`` / ``osv_snapshot``); a second run is fully
offline. This file is intentionally guard-independent: it imports no
``pipeline.guard`` code and makes no PASS/BLOCK decision -- only evidence.

Emits ``time_aligned_evidence.jsonl`` in the command 5.4 schema (+ a few audit
fields used by the labelers and the analysis).
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from pipeline.evidence import pypi_snapshot as P
from pipeline.evidence import osv_snapshot as O


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _pinned_version(row):
    """Exact pinned version for the change, or None for a range/unpinned spec."""
    v = (row.get("version_pin") or "").strip()
    return v or None


def _alignment_quality(pj, facts, pinned, ev_pkg_at, ev_ver):
    if pj is None:
        return "unresolved"            # package 404 now -> cannot recover PR-time state
    if pinned and ev_ver.get("version_upload_time") and facts.get("package_created_at"):
        return "exact"                 # have upload times on both ends
    if facts.get("package_created_at"):
        return "approximate"           # package creation known; version time maybe not
    return "current_only"              # only current existence is known


def build_one(row, pypi_dir, osv_dir):
    name = row.get("normalized_package_name") or row.get("package_name")
    pr_time = row.get("created_at")
    pinned = _pinned_version(row)

    pj = P.fetch_pypi(name, pypi_dir)
    oj = O.fetch_osv(name, osv_dir)
    facts = P.parse_pypi(pj) if pj else {"versions": {}, "exists": False,
                                          "package_created_at": None}

    exists_now = bool(pj) and bool(facts.get("exists"))
    exists_at = P.package_exists_at(facts, pr_time) if pj else False
    # Conservative existence-at-PR-time: definitively False if 404 now, or created
    # strictly after the PR; otherwise the computed value (None when undeterminable).
    if pj is None:
        pypi_exists_at = False
    elif exists_at is None:
        pypi_exists_at = True if exists_now else None
    else:
        pypi_exists_at = exists_at

    if pinned:
        vf = P.version_facts_at(facts, pinned, pr_time)
        version_exists_now = pinned in facts.get("versions", {})
        valid_version_at = vf["version_exists_at_pr_time"]
        upload_time = vf["version_upload_time"]
        yanked_at = vf["version_yanked_at_pr_time"]
    else:
        # range / unpinned: not a P2 candidate; resolution recorded separately.
        vf = {}
        version_exists_now = None
        valid_version_at = None
        upload_time = None
        yanked_at = None

    adv = O.advisory_facts(oj, pinned, pr_time) if pinned else {
        "direct_advisory_known_at_pr_time": False, "direct_advisory_ids": [],
        "advisory_published_at": None, "affected_range": None}

    # Advisories that DO cover the pinned version but were disclosed after the PR.
    post_ids = []
    if pinned:
        pdt = O._dt(pr_time)
        for vuln in (oj or {}).get("vulns", []) or []:
            pub = O._dt(vuln.get("published"))
            covers = any(O.version_in_range(a, pinned) for a in vuln.get("affected", []) or [])
            if covers and pub is not None and pdt is not None and pub > pdt:
                post_ids.append(vuln.get("id"))

    quality = _alignment_quality(pj, facts, pinned, pypi_exists_at, vf)

    return {
        "change_id": row.get("change_id"),
        "pr_id": row.get("pr_id"),
        "repo": row.get("repo_full_name"),
        "agent": row.get("agent_name"),
        "created_at": pr_time,
        "manifest_file": row.get("manifest_path"),
        "package_name": row.get("package_name"),
        "normalized_package_name": name,
        "new_spec": row.get("specifier_raw") or (f"=={pinned}" if pinned else None),
        "pinned_version": pinned,
        "change_type": row.get("change_type"),
        "is_new_dependency": row.get("is_new_dependency"),
        "evidence": {
            "pypi_exists_at_pr_time": pypi_exists_at,
            "pypi_exists_now": exists_now,
            "valid_version_at_pr_time": valid_version_at,
            "version_exists_now": version_exists_now,
            "version_upload_time": upload_time,
            "version_yanked_at_pr_time": yanked_at,
            "package_created_at": facts.get("package_created_at"),
            "direct_advisory_known_at_pr_time": adv["direct_advisory_known_at_pr_time"],
            "advisory_ids": adv["direct_advisory_ids"],
            "advisory_published_at": adv["advisory_published_at"],
            "affected_range": adv["affected_range"],
            "post_pr_disclosed_advisory_ids": post_ids,
            "evidence_urls": [
                f"https://pypi.org/pypi/{name}/json",
                f"https://api.osv.dev/v1/query (package={name}, ecosystem=PyPI)",
            ],
            "retrieved_at": _now_iso(),
            "time_alignment_quality": quality,
        },
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patches", default="outputs/tse_gap_closure/data/dependency_change_patches.jsonl")
    ap.add_argument("--out", default="outputs/tse_gap_closure/data/time_aligned_evidence.jsonl")
    ap.add_argument("--cache-dir", default="outputs/tse_gap_closure/data/evidence_cache")
    ap.add_argument("--workers", type=int, default=10)
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.patches).read_text().splitlines() if l.strip()]
    pypi_dir = Path(args.cache_dir) / "pypi"
    osv_dir = Path(args.cache_dir) / "osv"
    pypi_dir.mkdir(parents=True, exist_ok=True)
    osv_dir.mkdir(parents=True, exist_ok=True)

    out = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(build_one, r, pypi_dir, osv_dir) for r in rows]
        for fut in as_completed(futs):
            out.append(fut.result())
            done += 1
            if done % 100 == 0:
                print(f"  evidence {done}/{len(rows)}", flush=True)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Coverage summary.
    from collections import Counter
    q = Counter(r["evidence"]["time_alignment_quality"] for r in out)
    resolvable = sum(1 for r in out if r["evidence"]["time_alignment_quality"] != "unresolved")
    print(f"evidence for {len(out)} dependency changes -> {args.out}")
    print(f"  time_alignment_quality: {dict(q)}")
    print(f"  recoverable (not unresolved): {resolvable}/{len(out)} "
          f"({resolvable/max(1,len(out)):.1%})")


if __name__ == "__main__":
    main()

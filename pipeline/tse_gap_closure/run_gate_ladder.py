"""Run the guard gate ladder over the naturalistic dependency-change corpus.

Labels are fixed BEFORE this step (command 4.1/6). Here we only execute the
guard, using PR-TIME-aligned evidence so a gate sees a package/version/advisory
exactly as the public record stood when the PR was opened:

  * S1 existence   -> ``pypi_exists_at_pr_time``
  * S2 version     -> known_versions = versions uploaded on/before PR time
  * S3 direct vuln -> advisories published on/before PR time covering the pin
  * S5 license     -> PyPI license metadata

Variants (command 6):
  B0_no_gate, B1_scanner_fail_open, B1b_scanner_fail_closed,
  S1, S1S2, S1S2S3, S1S2S3+license, B3_full

B1/B1b are an OFF-THE-SHELF vulnerability scanner (pip-audit). A vulnerability
scanner structurally covers only published-CVE scope; it cannot represent a
nonexistent package or an invalid version pin -- that scope mismatch is the
point of EV-RQ1/EV-RQ3. pip-audit uses the current advisory DB (a superset of
PR-time knowledge), so any P1/P2 miss it shows is conservative / structural.
"""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from packaging.version import Version, InvalidVersion

from pipeline.evidence import pypi_snapshot as P
from pipeline.evidence import osv_snapshot as O
from pipeline.evidence.license_snapshot import license_from_pypi
from pipeline.external_realrisk.evidence_adapter import specifier_covering, _osv_severity, _license_label
from pipeline.guard.decision import run_guard
from pipeline.real_pr_mining.seeded_recall_scanner_matrix import _audit_json

GUARD_MODES = ["B0", "S1_only", "S1_S2", "S1_S2_S3", "S1_S2_S3_S5", "B3"]
# Map our ladder labels (command 6 naming) onto guard modes / scanner runs.
LADDER = [
    ("B0_no_gate", "guard", "B0"),
    ("B1_scanner_fail_open", "scanner", "fail_open"),
    ("B1b_scanner_fail_closed", "scanner", "fail_closed"),
    ("S1_existence", "guard", "S1_only"),
    ("S1S2_version", "guard", "S1_S2"),
    ("S1S2S3_direct_evidence", "guard", "S1_S2_S3"),
    ("S1S2S3_plus_license", "guard", "S1_S2_S3_S5"),
    ("B3_full_guard", "guard", "B3"),
]

_CT = {"add": "added", "version_change": "modified", "remove": "removed"}

DEFAULT_POLICY = {
    "allowed_licenses": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "PSF-2.0"],
    "blocked_licenses": ["GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0",
                         "GPL-2.0-only", "GPL-3.0-only", "AGPL-3.0-only"],
    "unknown_license_policy": "warn",
    "vulnerability_policy": {"min_blocked_severity": "HIGH"},
    "dependency_free_expected": False,
}


def _dep_change(row):
    pkg = row["package_name"]
    spec = row.get("specifier_raw") or ""
    return {"package": pkg, "change_type": _CT.get(row["change_type"], "added"),
            "new_line": f"{pkg}{spec}", "file": row.get("manifest_path", "requirements.txt")}


def _known_versions_at(facts, pr_time):
    """Versions whose earliest upload was on/before pr_time (PR-time release set)."""
    pdt = P._dt(pr_time)
    out = []
    for ver, v in facts.get("versions", {}).items():
        udt = P._dt(v.get("version_upload_time"))
        if pdt is not None and udt is not None and udt <= pdt:
            out.append(ver)
        elif pdt is None or udt is None:
            out.append(ver)  # cannot time-align this version -> keep (conservative)
    return out


def build_pr_time_evidence_refs(row, pj, oj):
    """guard evidence_refs reflecting the public record AT PR TIME."""
    pkg = row["package_name"]
    pinned = (row.get("version_pin") or "").strip() or None
    pr_time = row.get("created_at")
    facts = P.parse_pypi(pj) if pj else {"versions": {}, "exists": False, "package_created_at": None}

    exists_at = P.package_exists_at(facts, pr_time) if pj else False
    exists_now = bool(pj) and bool(facts.get("exists"))
    if pj is None:
        exists = False
    elif exists_at is None:
        exists = True if exists_now else None
    else:
        exists = exists_at

    known = _known_versions_at(facts, pr_time)
    spdx, missing = license_from_pypi(pj) if pj else (None, True)

    # advisories KNOWN at PR time covering the pinned version
    advisories = []
    if pinned:
        pdt = O._dt(pr_time)
        for vuln in (oj or {}).get("vulns", []) or []:
            pub = O._dt(vuln.get("published"))
            if not (pub is not None and pdt is not None and pub <= pdt):
                continue
            spec = None
            for aff in vuln.get("affected", []) or []:
                spec = specifier_covering(aff, pinned)
                if spec:
                    break
            if spec:
                advisories.append({"package": pkg, "affected_versions": spec,
                                   "cve": vuln.get("id"), "severity": _osv_severity(vuln),
                                   "description": vuln.get("summary") or "", "patched_in": None})

    return {
        "pypi_packages": {pkg: {"exists": exists, "known_versions": known, "license": spdx or ""}},
        "vulnerability_advisories": advisories,
        "license_metadata": {pkg: {"spdx": spdx, "adjudicated_label": _license_label(spdx, missing)}},
    }


def _scanner_decisions(req_line, audit_cache):
    audit = audit_cache.get(req_line, {"status": "tool_unavailable"})
    status = audit.get("status")
    vuln = status == "vulnerabilities_found"
    failed = status in {"tool_failure", "timeout", "tool_unavailable"}
    return {
        "B1_scanner_fail_open": "BLOCK" if vuln else "PASS",
        "B1b_scanner_fail_closed": "BLOCK" if (vuln or failed) else "PASS",
        "_scanner_status": status,
    }


def _precompute_scanner(rows, timeout, workers, cache_path):
    lines = sorted({_dep_change(r)["new_line"] for r in rows
                    if r["change_type"] in ("add", "version_change")})
    disk = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = [l for l in lines if l not in disk]
    print(f"pip-audit: {len(lines)} unique req lines, {len(disk)} cached, {len(todo)} to run", flush=True)
    if todo:
        done = [0]

        def run(line):
            return line, _audit_json(line, with_deps=False, timeout=timeout)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for line, res in ex.map(run, todo):
                disk[line] = res
                done[0] += 1
                if done[0] % 25 == 0:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(json.dumps(disk))
                    print(f"  pip-audit {done[0]}/{len(todo)}", flush=True)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(disk))
    return disk


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patches", default="outputs/tse_gap_closure/data/dependency_change_patches.jsonl")
    ap.add_argument("--out", default="outputs/tse_gap_closure/data/guard_outputs.jsonl")
    ap.add_argument("--cache-dir", default="outputs/tse_gap_closure/data/evidence_cache")
    ap.add_argument("--scanner-cache", default="outputs/tse_gap_closure/data/pip_audit_cache.json")
    ap.add_argument("--no-scanner", action="store_true")
    ap.add_argument("--timeout", type=int, default=40)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    rows = [json.loads(l) for l in Path(args.patches).read_text().splitlines() if l.strip()]
    pypi_dir = Path(args.cache_dir) / "pypi"
    osv_dir = Path(args.cache_dir) / "osv"

    audit_cache = ({} if args.no_scanner else
                   _precompute_scanner(rows, args.timeout, args.workers, Path(args.scanner_cache)))

    out = []
    for row in rows:
        name = row.get("normalized_package_name") or row["package_name"]
        pj = P.fetch_pypi(name, pypi_dir)
        oj = O.fetch_osv(name, osv_dir)
        ev = build_pr_time_evidence_refs(row, pj, oj)
        dep = [_dep_change(row)]

        decisions, fired = {}, {}
        for mode in GUARD_MODES:
            g = run_guard(dep, ev, DEFAULT_POLICY, mode=mode)
            fired[mode] = sorted({i.get("stage") for i in g.get("risk_report", [])})
        # map ladder labels
        gmap = {m: run_guard(dep, ev, DEFAULT_POLICY, mode=m)["decision"] for m in GUARD_MODES}
        ladder = {
            "B0_no_gate": gmap["B0"],
            "S1_existence": gmap["S1_only"],
            "S1S2_version": gmap["S1_S2"],
            "S1S2S3_direct_evidence": gmap["S1_S2_S3"],
            "S1S2S3_plus_license": gmap["S1_S2_S3_S5"],
            "B3_full_guard": gmap["B3"],
        }
        if not args.no_scanner:
            sc = _scanner_decisions(dep[0]["new_line"], audit_cache)
            ladder["B1_scanner_fail_open"] = sc["B1_scanner_fail_open"]
            ladder["B1b_scanner_fail_closed"] = sc["B1b_scanner_fail_closed"]
            scanner_status = sc["_scanner_status"]
        else:
            scanner_status = None

        out.append({
            "change_id": row.get("change_id"),
            "pr_id": row["pr_id"], "repo": row.get("repo_full_name"),
            "agent": row.get("agent_name"), "created_at": row.get("created_at"),
            "package_name": row["package_name"], "pinned_version": row.get("version_pin"),
            "change_type": row["change_type"], "manifest_path": row.get("manifest_path"),
            "decisions": ladder, "fired_stages": fired, "scanner_status": scanner_status,
        })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # quick block-rate sanity
    print(f"gate ladder over {len(out)} dependency changes -> {args.out}")
    variants = ["B0_no_gate", "B1_scanner_fail_open", "B1b_scanner_fail_closed",
                "S1_existence", "S1S2_version", "S1S2S3_direct_evidence",
                "S1S2S3_plus_license", "B3_full_guard"]
    for v in variants:
        blocked = sum(1 for r in out if r["decisions"].get(v) == "BLOCK")
        warned = sum(1 for r in out if r["decisions"].get(v) == "WARN")
        print(f"  {v:26s} BLOCK={blocked:4d} WARN={warned:4d} PASS={len(out)-blocked-warned:4d}")


if __name__ == "__main__":
    main()

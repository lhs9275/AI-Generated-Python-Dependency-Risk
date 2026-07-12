"""Evaluate the external-realrisk corpus across guard modes + pip-audit baseline.

For each record: rebuild the run_guard evidence_refs from the *cached real* PyPI/OSV
snapshots (no live calls unless a snapshot is missing), run the guard ladder, and run
pip-audit as the off-the-shelf scanner baseline. Emits one evaluation row per record.
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pipeline.evidence import pypi_snapshot as P
from pipeline.evidence import osv_snapshot as O
from pipeline.guard.decision import run_guard
from pipeline.external_realrisk.evidence_adapter import facts_to_evidence_refs
# Reuse the already-exercised pip-audit harness from the seeded experiment.
from pipeline.real_pr_mining.seeded_recall_scanner_matrix import _audit_json, _audit_issues

GUARD_MODES = ["B0", "S1_only", "S1_S2_S3", "B3"]

DEFAULT_POLICY = {
    "allowed_licenses": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "PSF-2.0"],
    "blocked_licenses": [
        "GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0",
        "GPL-2.0-only", "GPL-3.0-only", "AGPL-3.0-only",
    ],
    "unknown_license_policy": "warn",
    "vulnerability_policy": {"min_blocked_severity": "HIGH"},
    "dependency_free_expected": False,
}


def _dep_change(record: dict) -> list[dict]:
    pkg = record["package"]
    ver = record.get("version")
    line = f"{pkg}=={ver}" if ver else pkg
    return [{"package": pkg, "new_line": line, "change_type": "added",
             "file": record.get("manifest_file", "requirements.txt")}]


def _pip_audit_decisions(req_line: str, audit_cache: dict, with_deps_modes: tuple) -> dict:
    out = {}
    for with_deps in with_deps_modes:
        audit = audit_cache[(req_line, with_deps)]
        suffix = "with_deps" if with_deps else "no_deps"
        issues = _audit_issues(audit, f"pip_audit_{suffix}")
        failed = audit["status"] in {"tool_failure", "timeout", "tool_unavailable"}
        out[f"pip_audit_{suffix}_vuln_only"] = "BLOCK" if issues else "PASS"
        out[f"pip_audit_{suffix}_fail_closed"] = "BLOCK" if (issues or failed) else "PASS"
    return out


def _ckey(line, wd):
    return f"{line}|{'deps' if wd else 'nodeps'}"


def _precompute_audits(records, with_deps_modes, timeout, workers, cache_path: Path) -> dict:
    """Run pip-audit for every (unique req_line, mode), with a resumable disk cache.

    Each completed result is flushed to ``cache_path`` immediately, so a killed run
    resumes from where it stopped on the next invocation (only missing keys re-run).
    """
    lines = sorted({(f"{r['package']}=={r['version']}" if r.get("version") else r["package"])
                    for r in records})
    keys = [(line, wd) for line in lines for wd in with_deps_modes]

    disk = {}
    if cache_path.exists():
        disk = json.loads(cache_path.read_text())
    todo = [k for k in keys if _ckey(*k) not in disk]
    print(f"pip-audit: {len(keys)} total, {len(disk)} cached, {len(todo)} to run, "
          f"{workers} workers", flush=True)
    done = [0]

    def run(key):
        line, wd = key
        res = _audit_json(line, with_deps=wd, timeout=timeout)
        return key, res

    if todo:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for key, res in ex.map(run, todo):
                disk[_ckey(*key)] = res
                done[0] += 1
                if done[0] % 10 == 0:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(json.dumps(disk))
                    print(f"  pip-audit {done[0]}/{len(todo)}", flush=True)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(disk))
    return {(line, wd): disk[_ckey(line, wd)] for line, wd in keys}


def evaluate(records: list[dict], cache_dir: Path, timeout: int, run_scanner: bool,
             with_deps: bool = True, workers: int = 8,
             audit_cache_path: Path = None) -> list[dict]:
    pypi_dir, osv_dir = cache_dir / "pypi", cache_dir / "osv"
    with_deps_modes = (False, True) if with_deps else (False,)
    if audit_cache_path is None:
        audit_cache_path = Path("results/external_realrisk_py/pip_audit_cache.json")
    audit_cache = (_precompute_audits(records, with_deps_modes, timeout, workers, audit_cache_path)
                   if run_scanner else {})
    rows = []
    for rec in records:
        name = rec["package"]
        pj = P.fetch_pypi(name, pypi_dir)          # cache hit (sourced earlier)
        oj = O.fetch_osv(name, osv_dir)
        ev = facts_to_evidence_refs(rec, pj, oj)
        dep = _dep_change(rec)

        decisions, detail = {}, {}
        for mode in GUARD_MODES:
            g = run_guard(dep, ev, DEFAULT_POLICY, mode=mode)
            decisions[mode] = g["decision"]
            detail[mode] = [i.get("stage") for i in g.get("risk_report", [])]

        if run_scanner:
            pa = _pip_audit_decisions(dep[0]["new_line"], audit_cache, with_deps_modes)
            decisions.update(pa)
            decisions["B1_scanner"] = pa["pip_audit_no_deps_vuln_only"]

        rows.append({
            "record_id": rec["record_id"],
            "label": rec["label"],
            "risk_family": rec["risk_family"],
            "primary": rec["primary"],
            "risk_label": rec["risk_label"],
            "source_type": rec["source_type"],
            "package": name,
            "version": rec.get("version"),
            "evidence_external_id": rec.get("evidence_external_id"),
            "decisions": decisions,
            "fired_stages": detail,
        })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--records", type=Path,
                    default=Path("data/external_realrisk_py/records.jsonl"))
    ap.add_argument("--cache-dir", type=Path,
                    default=Path("data/external_realrisk_py/evidence_snapshots"))
    ap.add_argument("--out", type=Path,
                    default=Path("results/external_realrisk_py/evaluation.jsonl"))
    ap.add_argument("--timeout", type=int, default=40)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-scanner", action="store_true",
                    help="skip pip-audit baseline (guard modes only)")
    ap.add_argument("--no-deps-only", action="store_true",
                    help="run pip-audit in --no-deps mode only (faster)")
    args = ap.parse_args()

    records = [json.loads(l) for l in args.records.read_text().splitlines() if l.strip()]
    rows = evaluate(records, args.cache_dir, args.timeout, run_scanner=not args.no_scanner,
                    with_deps=not args.no_deps_only, workers=args.workers)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"evaluated {len(rows)} records -> {args.out}")
    # quick recall sanity per mode
    risky = [r for r in rows if r["label"] == "risky"]
    for m in GUARD_MODES + (["B1_scanner"] if not args.no_scanner else []):
        blk = sum(1 for r in risky if r["decisions"].get(m) == "BLOCK")
        print(f"  {m}: blocked {blk}/{len(risky)} risky")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Independent npm external real-evidence recall corpus + gate evaluation.

npm analogue of the PyPI Workstream-K external recall corpus
(pipeline/external_realrisk/source_records.py + metrics.py). Its purpose is to break
the circularity that the naturalistic gate-on-our-own-labels would otherwise have:
the RISKY side here is sourced from PUBLIC databases (OSV `MAL-` malicious-package
advisories, real GHSA HIGH/CRITICAL vulnerabilities) INDEPENDENTLY of our F1/F2/F3
labeler, and the NORMAL side is real registry-resolvable packages at safe versions.
The gate never sees how a record was labeled.

Families (mirrors PyPI 107-record corpus 52 risky / 55 normal):
  * S1  package_nonexistent : OSV MAL- npm packages now returning 404 on the registry
  * S2  version_nonexistent : real packages with a version bumped past the latest release
  * S3  direct_cve          : real packages with a real HIGH/CRITICAL GHSA covering a
                              concrete published version
  * NONE normal             : real packages at a safe version, no covering advisory

Outputs results/npm_external_recall.json (recall matrix per guard ladder + npm-audit
baseline) and the corpus + scoped caches so it reproduces offline.

Source of MAL-/GHSA enumeration: the OSV per-ecosystem bulk export
  https://osv-vulnerabilities.storage.googleapis.com/npm/all.zip
(downloaded once to a scratch dir, never committed).
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import zipfile
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))
import npm_gate  # noqa: E402
from npm_gate import evaluate, MODES  # noqa: E402
from npm_evidence import fetch_registry_slim, iso, _affects  # noqa: E402
from npm_semver import parse_version, is_prerelease  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "external_realrisk"))
from metrics import compute_recall_matrix  # noqa: E402

OSV_NPM_EXPORT = "https://osv-vulnerabilities.storage.googleapis.com/npm/all.zip"
EVAL_TIME = "2026-06-30T00:00:00Z"          # frozen present-time snapshot (reproducible)

TARGET_S1 = 20
TARGET_S3 = 20
TARGET_S2 = 12
TARGET_NORMAL = 55

# real, mainstream packages for S2 stress (impossible version) + normal pool
STAPLES = [
    "react", "react-dom", "vue", "express", "lodash", "axios", "chalk", "commander",
    "debug", "dotenv", "classnames", "uuid", "zod", "yargs", "rxjs", "dayjs",
    "prettier", "eslint", "typescript", "webpack", "vite", "rollup", "jest",
    "mocha", "chai", "cors", "body-parser", "morgan", "ws", "glob", "fs-extra",
    "semver", "picocolors", "nanoid", "tslib", "core-js", "node-fetch", "qs",
    "minimatch", "cross-spawn", "ignore", "ora", "inquirer", "execa", "globby",
    "pino", "winston", "joi", "ajv", "fast-glob", "p-limit", "tiny-invariant",
    "deepmerge", "lru-cache", "graceful-fs", "resolve", "which", "is-glob",
]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def download_export(scratch):
    """Download the npm OSV export once into `scratch`; return path."""
    path = os.path.join(scratch, "osv_npm_all.zip")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    log(f"downloading {OSV_NPM_EXPORT} ...")
    req = Request(OSV_NPM_EXPORT, headers={"User-Agent": "ASG-npm-gate"})
    with urlopen(req, timeout=300) as r, open(path, "wb") as f:
        f.write(r.read())
    log(f"  -> {os.path.getsize(path)/1e6:.1f} MB")
    return path


def iter_advisories(zip_path):
    """Yield each OSV advisory dict from the export zip."""
    with zipfile.ZipFile(zip_path) as z:
        for nm in z.namelist():
            if not nm.endswith(".json"):
                continue
            try:
                yield json.loads(z.read(nm))
            except Exception:
                continue


def _npm_affected(adv):
    """First npm affected-entry of an advisory, or None."""
    for a in adv.get("affected", []):
        if a.get("package", {}).get("ecosystem", "").lower() == "npm":
            return a
    return None


def _concrete_vuln_version(name, aff, reg_cache):
    """A real published version of `name` that the advisory `aff` actually covers."""
    slim = reg_cache.get(name)
    if slim is None:
        slim = reg_cache[name] = fetch_registry_slim(name)
        time.sleep(0.05)
    if not slim or not slim.get("exists"):
        return None
    pubvers = list((slim.get("versions") or {}).keys())
    adv_stub = {"affected": [aff]}
    # require a CONCRETE published release (parseable, non-prerelease) the advisory
    # covers -- skip "0.0.1-security"/"x-preview" takedown stubs, which npm semver
    # never resolves and which are really removal markers, not installable vulns.
    def _concrete(v):
        return parse_version(v) is not None and not is_prerelease(v)

    for v in (aff.get("versions") or []):
        if v in pubvers and _concrete(v) and _affects(adv_stub, v):
            return v
    for v in pubvers:
        if not _concrete(v):
            continue
        if _affects(adv_stub, v):
            return v
    return None


def build_corpus(zip_path, reg_cache, osv_sev_cache):
    records = []
    seen_names = set()

    # ---- S3: real HIGH/CRITICAL GHSA on a concrete published version ----------
    # ---- S1: MAL- packages that now 404 -------------------------------------
    s1, s3 = [], []
    for adv in iter_advisories(zip_path):
        aid = adv.get("id", "")
        if len(s1) >= TARGET_S1 and len(s3) >= TARGET_S3:
            break
        aff = _npm_affected(adv)
        if not aff:
            continue
        name = aff.get("package", {}).get("name")
        if not name or name in seen_names:
            continue

        if aid.startswith("MAL-") and len(s1) < TARGET_S1:
            slim = reg_cache.get(name)
            if slim is None:
                slim = reg_cache[name] = fetch_registry_slim(name)
                time.sleep(0.05)
            if slim and slim.get("exists") is False:        # confirmed taken-down
                seen_names.add(name)
                s1.append({"record_id": f"S1::{name}", "label": "risky", "family": "S1",
                           "primary": True, "name": name, "spec": "*",
                           "source": aid, "note": "OSV malicious-package advisory; 404 on registry now"})
            continue

        if aid.startswith("GHSA-") and len(s3) < TARGET_S3:
            sev = (adv.get("database_specific") or {}).get("severity")
            sev = npm_gate._sev_norm(sev)
            if sev not in ("HIGH", "CRITICAL"):
                continue
            ver = _concrete_vuln_version(name, aff, reg_cache)
            if not ver:
                continue
            seen_names.add(name)
            s3.append({"record_id": f"S3::{name}@{ver}", "label": "risky", "family": "S3",
                       "primary": True, "name": name, "spec": ver,
                       "source": aid, "severity": sev,
                       "note": f"{sev} {aid} covers published {name}@{ver}"})

    records += s1 + s3

    # ---- S2: real packages, version bumped past latest (guaranteed absent) ----
    s2 = []
    for name in STAPLES:
        if len(s2) >= TARGET_S2:
            break
        if name in seen_names:
            continue
        slim = reg_cache.get(name)
        if slim is None:
            slim = reg_cache[name] = fetch_registry_slim(name)
            time.sleep(0.05)
        if slim and slim.get("exists"):
            seen_names.add(name)
            s2.append({"record_id": f"S2::{name}@999.0.0", "label": "risky", "family": "S2",
                       "primary": True, "name": name, "spec": "999.0.0",
                       "source": "constructed", "note": "exact pin past latest release -> never published"})
    records += s2

    # ---- NONE: real packages at a safe published version, no covering advisory -
    normal = []
    for name in STAPLES:
        if len(normal) >= TARGET_NORMAL:
            break
        if name in seen_names:
            continue
        slim = reg_cache.get(name)
        if slim is None:
            slim = reg_cache[name] = fetch_registry_slim(name)
            time.sleep(0.05)
        if not slim or not slim.get("exists"):
            continue
        # highest published STABLE (non-prerelease), advisory-free release at eval_time
        # -- concrete so the gate actually evaluates S2/S3 and PASSes on merit, not
        # because an unparseable prerelease spec was non-evaluable.
        vers = sorted([v for v in (slim.get("versions") or {})
                       if parse_version(v) and not is_prerelease(v)],
                      key=parse_version, reverse=True)
        chosen = None
        for v in vers[:40]:
            advs = npm_gate._advisories_at(name, v, EVAL_TIME, osv_sev_cache)
            if not advs:
                chosen = v
                break
        if chosen:
            seen_names.add(name)
            normal.append({"record_id": f"NONE::{name}@{chosen}", "label": "normal",
                           "family": "NONE", "primary": False, "name": name, "spec": chosen,
                           "source": "registry", "note": "real package, safe version, no covering advisory"})
    records += normal
    return records


def run(records, reg_cache, osv_sev_cache):
    rows = []
    for rec in records:
        res = evaluate(rec["name"], rec["spec"], EVAL_TIME, reg_cache, osv_sev_cache)
        rows.append({**rec,
                     "resolved": res["resolved"],
                     "stage_dec": res["stage_dec"],
                     "advisories": res["advisories"],
                     "decisions": res["decisions"]})
    return rows


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results = os.path.join(here, "results")
    scratch = os.environ.get("SCRATCH", os.path.join(here, "scratch"))
    os.makedirs(scratch, exist_ok=True)

    reg_path = os.path.join(results, "npm_gate_reg_cache.json")
    sev_path = os.path.join(results, "npm_gate_osv_sev_cache.json")
    reg_cache = json.load(open(reg_path)) if os.path.exists(reg_path) else {}
    osv_sev_cache = json.load(open(sev_path)) if os.path.exists(sev_path) else {}

    zip_path = download_export(scratch)
    log("building corpus ...")
    records = build_corpus(zip_path, reg_cache, osv_sev_cache)
    by_fam = {}
    for r in records:
        by_fam[r["family"]] = by_fam.get(r["family"], 0) + 1
    log(f"corpus: {len(records)} records {by_fam}")

    rows = run(records, reg_cache, osv_sev_cache)
    matrix = compute_recall_matrix(rows)

    out = {
        "eval_time": EVAL_TIME,
        "operationalization": "independent of the F1/F2/F3 labeler; risky from OSV MAL-/GHSA, "
                              "normal real registry-resolvable; core gate S1+S2+S3 mirrored from "
                              "guard/decision.py; npm_audit baseline = S3-only fail-closed",
        "n": len(rows),
        "family_counts": by_fam,
        "headline_mode": "S1_S2_S3",
        "baseline_mode": "npm_audit",
        "matrix": matrix,
        "modes": MODES,
        "note": "no human labeling; npm analogue of the PyPI Workstream-K external recall corpus",
    }
    json.dump(out, open(os.path.join(results, "npm_external_recall.json"), "w"), indent=2)
    with open(os.path.join(results, "npm_external_recall_corpus.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    json.dump(reg_cache, open(reg_path, "w"))
    json.dump(osv_sev_cache, open(sev_path, "w"))

    core = matrix["modes"]["S1_S2_S3"]
    base = matrix["modes"]["npm_audit"]
    log(f"\nCORE S1_S2_S3  block-recall={core['recall']:.3f} CI{core['recall_ci']} "
        f"detect={core['detection_recall']:.3f} false-block={core['false_block_rate']} "
        f"precision={core['precision']}")
    log(f"npm_audit base block-recall={base['recall']:.3f} false-block={base['false_block_rate']}")
    log(f"per-family core recall: " +
        ", ".join(f"{k}={v['blocked']}/{v['n']}" for k, v in core["family_recall"].items()))


if __name__ == "__main__":
    main()

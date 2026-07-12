#!/usr/bin/env python3
"""PR-time-anchored npm public evidence (registry + OSV).

Mirrors the PyPI evidence reconstruction (pipeline/evidence/pypi_snapshot.py +
osv_snapshot.py): every fact is gated to the PR creation time so F1/F2/F3 reflect
what was PUBLICLY KNOWN WHEN THE PR WAS OPENED, not today's state. This removes
the live-vs-frozen confound -- an advisory disclosed AFTER the PR, or a package/
version published AFTER the PR, must not count, exactly as in the PyPI study
(advisory published <= pr_time; package created <= pr_time; version uploaded
<= pr_time).

Returns slim, cacheable structures (created-ts + version->upload-ts map; advisory
id+published+affected ranges) -- the minimum needed to re-derive verdicts, never
the full (large) registry document.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, os.path.dirname(__file__))
from npm_semver import parse_version, max_satisfying, UNPARSEABLE  # noqa: E402

NPM_REGISTRY = "https://registry.npmjs.org"
OSV_API = "https://api.osv.dev/v1/query"


def iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _enc(name: str) -> str:
    return quote(name, safe="@").replace("/", "%2F")


# ---- registry (existence + version upload times), slim-cached -----------------

def fetch_registry_slim(name: str):
    """Slim registry facts for `name`:
        {"exists": True, "created": iso, "versions": {ver: upload_iso}}
      | {"exists": False}                         (confirmed 404 -> absent)
      | None                                       (network error -> undeterminable)
    Pulls the full doc once (needs the `time` map) but persists only the slim form."""
    req = Request(f"{NPM_REGISTRY}/{_enc(name)}",
                  headers={"User-Agent": "ASG-npm-evidence", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            doc = json.loads(r.read())
    except HTTPError as e:
        if e.code == 404:
            return {"exists": False}
        return None
    except Exception:
        return None
    times = doc.get("time", {}) or {}
    versions = {v: times.get(v) for v in (doc.get("versions") or {}).keys()}
    return {"exists": True, "created": times.get("created"), "versions": versions}


def reconstruct(name: str, spec: str, pr_time, reg_cache: dict):
    """PR-time evidence for one (name, spec). reg_cache: name -> slim dict|None.
    Returns {exists_at_pr, versions_at_pr, resolved, note}."""
    prt = iso(pr_time)
    if name not in reg_cache:
        reg_cache[name] = fetch_registry_slim(name)
        time.sleep(0.08)
    slim = reg_cache[name]

    ev = {"exists_at_pr": None, "versions_at_pr": [], "resolved": None, "note": ""}
    if slim is None:
        ev["note"] = "registry error"
        return ev
    if slim.get("exists") is False:
        ev["exists_at_pr"] = False               # absent now -> absent at PR (F1)
        return ev

    created = iso(slim.get("created"))
    if prt is not None and created is not None:
        ev["exists_at_pr"] = (created <= prt)    # registered after PR -> didn't exist
    else:
        ev["exists_at_pr"] = True                # exists, no usable ts -> assume existed
    if ev["exists_at_pr"] is False:
        return ev

    vatp = []
    for v, up in (slim.get("versions") or {}).items():
        upt = iso(up)
        if prt is None or upt is None or upt <= prt:
            vatp.append(v)
    ev["versions_at_pr"] = vatp
    ev["resolved"] = max_satisfying(spec, vatp)
    return ev


# ---- OSV (advisories), PR-time disclosure gate, slim-cached -------------------

def fetch_osv_slim(name: str):
    """Slim OSV facts: [{"id","published","affected":[{versions,ranges}]}] for npm,
    [] if none, None on error."""
    payload = json.dumps({"package": {"ecosystem": "npm", "name": name}}).encode()
    req = Request(OSV_API, data=payload,
                  headers={"User-Agent": "ASG-npm-evidence",
                           "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            vulns = json.loads(r.read()).get("vulns") or []
    except Exception:
        return None
    out = []
    for v in vulns:
        aff = []
        for a in v.get("affected", []):
            pkg = a.get("package", {})
            if pkg.get("ecosystem", "").lower() != "npm":
                continue
            aff.append({"versions": a.get("versions") or [],
                        "ranges": [{"type": rng.get("type"),
                                    "events": rng.get("events", [])}
                                   for rng in a.get("ranges", [])]})
        out.append({"id": v.get("id"), "published": v.get("published"), "affected": aff})
    return out


def _affects(adv, version: str) -> bool:
    """Does advisory `adv` (slim) affect npm `version`? Exact `versions` list, then
    SEMVER/ECOSYSTEM introduced..fixed/last_affected ranges."""
    vt = parse_version(version)
    for a in adv.get("affected", []):
        if version in (a.get("versions") or []):
            return True
        if vt is None:
            continue
        for rng in a.get("ranges", []):
            if rng.get("type") not in ("SEMVER", "ECOSYSTEM"):
                continue
            lo, hi_excl, hi_incl = (0, 0, 0), None, None
            for ev in rng.get("events", []):
                if "introduced" in ev:
                    lo = (0, 0, 0) if ev["introduced"] == "0" else parse_version(ev["introduced"])
                elif "fixed" in ev:
                    hi_excl = parse_version(ev["fixed"])
                elif "last_affected" in ev:
                    hi_incl = parse_version(ev["last_affected"])
            if lo is None:
                continue
            if vt < lo:
                continue
            if hi_excl is not None and vt >= hi_excl:
                continue
            if hi_incl is not None and vt > hi_incl:
                continue
            return True
    return False


def advisory_ids_at_pr(name: str, version, pr_time, osv_cache: dict):
    """OSV ids affecting `version` that were PUBLICLY DISCLOSED on/before pr_time.
    Empty when version is None/unparseable or no PR-time-known advisory hits."""
    if not version or version == UNPARSEABLE:
        return []
    if name not in osv_cache:
        osv_cache[name] = fetch_osv_slim(name)
        time.sleep(0.08)
    advs = osv_cache[name]
    if not advs:
        return []
    prt = iso(pr_time)
    ids = []
    for a in advs:
        pub = iso(a.get("published"))
        if prt is not None and pub is not None and pub > prt:
            continue                              # disclosed AFTER the PR -> excluded
        if _affects(a, version):
            ids.append(a.get("id"))
    return ids

#!/usr/bin/env python3
"""npm PR-time public-evidence GATE -- faithful npm port of pipeline/guard/decision.py.

Scope = the CORE public-evidence trio S1 + S2 + S3, which the PyPI study shows already
attains full-B3 external-corpus block recall (0.981); S4/S5/S6 add no value on that
corpus, so the cross-ecosystem port replicates the load-bearing core, not the policy
stages whose generality (license norms, restraint policy) is itself ecosystem-specific.

Block rule mirrored 1:1 with guard/decision.py:
  * S1 (existence):  package absent at evaluation time  -> critical -> BLOCK
                     existence undeterminable (net error) -> warn   -> WARN
  * S2 (version):    exact pin not in versions published <= eval_time -> critical -> BLOCK
  * S3 (direct CVE): advisory disclosed <= eval_time covering the resolved version,
                     severity >= min_blocked (default HIGH) -> critical -> BLOCK;
                     a covering advisory below threshold       -> warn     -> WARN
  * aggregate: ANY critical -> BLOCK, else ANY warn -> WARN, else PASS.

Evidence is anchored to `eval_time` exactly as the PyPI gate freezes its snapshot at the
PR creation date (PR time for the naturalistic corpus; a frozen present-time constant for
the constructed external recall corpus, matching Workstream K's now-404 selection).

No human labeling anywhere -- every stage is a deterministic function of public
registry/OSV state.
"""
from __future__ import annotations

import json
import os
import sys
import time
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(__file__))
from npm_evidence import reconstruct, iso, OSV_API  # noqa: E402
from npm_semver import UNPARSEABLE  # noqa: E402
from npm_dep_extract import is_exact_pin  # noqa: E402

# qualitative severity rank; MODERATE is GHSA's name for MEDIUM
_RANK = {"LOW": 1, "MODERATE": 2, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

# the guard ladders we evaluate, expressed as the set of enabled stages.
#   npm_audit = the `npm audit` analogue baseline: it can only surface a *known
#   advisory* on an installed package (S3), and -- like pip-audit -- structurally
#   cannot flag a non-existent package (S1) or an invalid pinned version (S2);
#   modeled as fail-closed (blocks on ANY covering advisory, any severity).
_MODE_STAGES = {
    "B0": set(),
    "S1_only": {"S1"},
    "S1_S2": {"S1", "S2"},
    "S1_S2_S3": {"S1", "S2", "S3"},   # core gate (headline)
    "npm_audit": {"S3_audit"},
}


def _sev_norm(s):
    if not s:
        return None
    s = str(s).upper()
    return "MEDIUM" if s == "MODERATE" else s


def fetch_osv_sev(name: str):
    """Like npm_evidence.fetch_osv_slim but retains advisory severity.
    Returns [{id, published, severity, affected}] for npm, [] if none, None on error.
    Severity from database_specific.severity (GHSA's qualitative band); None if absent."""
    payload = json.dumps({"package": {"ecosystem": "npm", "name": name}}).encode()
    req = Request(OSV_API, data=payload,
                  headers={"User-Agent": "ASG-npm-gate", "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as r:
            vulns = json.loads(r.read()).get("vulns") or []
    except Exception:
        return None
    out = []
    for v in vulns:
        sev = _sev_norm((v.get("database_specific") or {}).get("severity"))
        aff = []
        for a in v.get("affected", []):
            pkg = a.get("package", {})
            if pkg.get("ecosystem", "").lower() != "npm":
                continue
            aff.append({"versions": a.get("versions") or [],
                        "ranges": [{"type": rng.get("type"),
                                    "events": rng.get("events", [])}
                                   for rng in a.get("ranges", [])]})
        out.append({"id": v.get("id"), "published": v.get("published"),
                    "severity": sev, "affected": aff})
    return out


def _advisories_at(name, version, eval_time, osv_sev_cache):
    """Severity-bearing advisories covering `version`, disclosed <= eval_time."""
    from npm_evidence import _affects  # local: reuse the exact range logic
    if not version or version == UNPARSEABLE:
        return []
    if name not in osv_sev_cache:
        osv_sev_cache[name] = fetch_osv_sev(name)
        time.sleep(0.08)
    advs = osv_sev_cache[name]
    if not advs:
        return []
    prt = iso(eval_time)
    hits = []
    for a in advs:
        pub = iso(a.get("published"))
        if prt is not None and pub is not None and pub > prt:
            continue
        if _affects(a, version):
            hits.append(a)
    return hits


def evaluate(name, spec, eval_time, reg_cache, osv_sev_cache, min_sev="HIGH"):
    """Run the npm gate stages for one (name, spec) at eval_time.

    Returns {stage_dec: {S1,S2,S3,S3_audit}, resolved, advisories, decisions: {mode: PASS|WARN|BLOCK}}.
    stage_dec values are PASS|WARN|BLOCK; S3_audit is the baseline's S3 (blocks on any advisory)."""
    ev = reconstruct(name, spec, eval_time, reg_cache)
    resolved = ev.get("resolved")
    stage = {}

    # --- S1: existence -------------------------------------------------------
    if ev["exists_at_pr"] is False:
        stage["S1"] = "BLOCK"
    elif ev["exists_at_pr"] is None:
        stage["S1"] = "WARN"          # network-undeterminable -> warn, never silent pass
    else:
        stage["S1"] = "PASS"

    # --- S2: version validity (exact pin absent at eval_time) -----------------
    pinned = is_exact_pin(spec)
    if ev["exists_at_pr"] and pinned and pinned not in set(ev.get("versions_at_pr") or []):
        stage["S2"] = "BLOCK"
    else:
        stage["S2"] = "PASS"

    # --- S3: direct vulnerability --------------------------------------------
    advs = []
    if ev["exists_at_pr"] and resolved and resolved != UNPARSEABLE:
        advs = _advisories_at(name, resolved, eval_time, osv_sev_cache)
    if advs:
        worst = max((_RANK.get(a.get("severity") or "", 0) for a in advs), default=0)
        stage["S3"] = "BLOCK" if worst >= _RANK[min_sev] else "WARN"
        stage["S3_audit"] = "BLOCK"   # npm-audit analogue: any covering advisory
    else:
        stage["S3"] = "PASS"
        stage["S3_audit"] = "PASS"

    decisions = {}
    for mode, enabled in _MODE_STAGES.items():
        decs = [stage[s] for s in enabled]
        if "BLOCK" in decs:
            decisions[mode] = "BLOCK"
        elif "WARN" in decs:
            decisions[mode] = "WARN"
        else:
            decisions[mode] = "PASS"

    return {"stage_dec": {k: stage[k] for k in ("S1", "S2", "S3", "S3_audit")},
            "resolved": resolved,
            "advisories": [{"id": a.get("id"), "severity": a.get("severity")} for a in advs],
            "decisions": decisions}


MODES = list(_MODE_STAGES.keys())

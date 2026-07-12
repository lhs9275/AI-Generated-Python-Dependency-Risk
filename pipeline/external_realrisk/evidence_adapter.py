"""Turn real PyPI/OSV facts into the run_guard evidence_refs contract.

run_guard consumes ``evidence_refs`` shaped as::

    {
      "pypi_packages": {pkg: {"exists": bool, "known_versions": [...], "license": str}},
      "vulnerability_advisories": [{"package", "affected_versions", "cve",
                                    "severity", "description", "patched_in"}],
      "license_metadata": {pkg: {"spdx": str|None, "adjudicated_label": str}},
    }

Every field here is derived from a *real* PyPI JSON response and a *real* OSV
query response (no seeded/synthetic snapshots). The only non-trivial transform
is mapping an OSV ``affected`` range to a PEP 440 specifier string that the S3
stage can parse, which is what ``specifier_covering`` does.
"""

from packaging.specifiers import SpecifierSet, InvalidSpecifier
from packaging.version import Version, InvalidVersion

from pipeline.evidence.pypi_snapshot import parse_pypi
from pipeline.evidence.license_snapshot import license_from_pypi


_SEV_MAP = {"CRITICAL": "critical", "HIGH": "high", "MODERATE": "medium",
            "MEDIUM": "medium", "LOW": "low"}


def _v(s):
    try:
        return Version(str(s))
    except (InvalidVersion, TypeError):
        return None


def _branch_specifier(intro, hi, hi_inclusive):
    """PEP 440 specifier for a single [intro, hi) / [intro, hi] branch.

    ``intro``/``hi`` are strings or None (None = unbounded that side; "0" intro
    is treated as unbounded-low). Returns the specifier string.
    """
    clauses = []
    if intro not in (None, "0", 0):
        clauses.append(f">={intro}")
    if hi is not None:
        clauses.append(f"<={hi}" if hi_inclusive else f"<{hi}")
    return ",".join(clauses) if clauses else ">=0"


def _branches(affected):
    """Yield (intro, hi, hi_inclusive) for each affected interval in a range."""
    for rng in affected.get("ranges", []) or []:
        if rng.get("type") not in ("ECOSYSTEM", "SEMVER", None):
            continue
        intro = None
        open_interval = False
        for ev in rng.get("events", []) or []:
            if "introduced" in ev:
                intro = ev["introduced"]
                open_interval = True
            elif "fixed" in ev and open_interval:
                yield (intro, ev["fixed"], False)
                open_interval = False
            elif "last_affected" in ev and open_interval:
                yield (intro, ev["last_affected"], True)
                open_interval = False
        if open_interval:  # introduced, never fixed
            yield (intro, None, False)


def specifier_covering(affected: dict, version: str) -> str | None:
    """PEP 440 specifier for the branch of an OSV ``affected`` entry holding ``version``.

    Returns None when ``version`` falls in no branch of this entry. Explicit
    ``versions`` lists collapse to ``==version`` when the version is listed.
    """
    explicit = affected.get("versions")
    if explicit:
        return f"=={version}" if version in explicit else None

    target = _v(version)
    if target is None:
        return None
    for intro, hi, hi_inclusive in _branches(affected):
        lo = _v(intro) if intro not in (None, "0", 0) else None
        hi_v = _v(hi) if hi is not None else None
        in_branch = (lo is None or target >= lo) and (
            hi_v is None
            or (target <= hi_v if hi_inclusive else target < hi_v))
        if in_branch:
            spec = _branch_specifier(intro, hi, hi_inclusive)
            try:
                SpecifierSet(spec)
            except InvalidSpecifier:
                return None
            return spec
    return None


def _osv_severity(vuln: dict) -> str:
    """Best-effort severity label (low/medium/high/critical) from an OSV vuln."""
    ds = (vuln.get("database_specific") or {}).get("severity")
    if ds:
        return _SEV_MAP.get(str(ds).upper(), str(ds).lower())
    for sev in vuln.get("severity", []) or []:
        # CVSS vectors are present but unscored here; treat any CVSS as high.
        if sev.get("type", "").startswith("CVSS"):
            return "high"
    return "high"  # advisories with no severity default to a blocking level


def _license_label(spdx, missing) -> str:
    if missing or not spdx:
        return "missing"
    s = spdx.lower()
    if any(tok in s for tok in ("agpl", "lgpl", "gpl")):
        return "blocked"
    return "allowed"


def facts_to_evidence_refs(record: dict, pypi_json, osv_json) -> dict:
    """Build a run_guard evidence_refs dict from real PyPI/OSV responses.

    ``record`` carries at least ``package`` and (for version/CVE risks) ``version``.
    ``pypi_json`` is the raw PyPI JSON (or None for a 404 / nonexistent package).
    ``osv_json`` is the raw OSV query response (or {} when none).

    Only advisories whose affected range covers ``record['version']`` are emitted,
    so S3 fires exactly on the documented vulnerable version.
    """
    pkg = record["package"]
    version = record.get("version")

    exists = pypi_json is not None and bool(
        pypi_json.get("info") or pypi_json.get("releases"))
    facts = parse_pypi(pypi_json) if pypi_json else {"versions": {}}
    known = sorted(facts.get("versions", {}).keys())
    spdx, missing = license_from_pypi(pypi_json) if pypi_json else (None, True)

    advisories = []
    for vuln in (osv_json or {}).get("vulns", []) or []:
        spec = None
        for aff in vuln.get("affected", []) or []:
            if version:
                spec = specifier_covering(aff, version)
                if spec:
                    break
        if not spec:
            continue
        advisories.append({
            "package": pkg,
            "affected_versions": spec,
            "cve": vuln.get("id"),
            "severity": _osv_severity(vuln),
            "description": vuln.get("summary") or vuln.get("details") or "",
            "patched_in": None,
        })

    return {
        "pypi_packages": {pkg: {"exists": exists, "known_versions": known,
                                "license": spdx or ""}},
        "vulnerability_advisories": advisories,
        "license_metadata": {pkg: {"spdx": spdx,
                                   "adjudicated_label": _license_label(spdx, missing)}},
    }

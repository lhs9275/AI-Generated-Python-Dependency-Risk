#!/usr/bin/env python3
"""label_B.py — Independent (labeler_B) dependency-risk labeler.

This module is a deliberately SELF-CONTAINED re-implementation. It does NOT
import or read anything under ``pipeline/`` (no guard / evidence / tse_gap_closure
helpers), and it does NOT read the other labeler's inputs/outputs
(``time_aligned_evidence.jsonl`` or ``labels_A.csv``).

It reconstructs, for each dependency change, the public evidence as it stood at
PR creation time by querying PyPI and OSV directly (with its own HTTP fetching,
its own response parsing, its own PEP 440 range logic, and its own
time-alignment). Network responses are cached on disk so reruns are offline.

Primary label (single most severe that applies, else NONE):
  P1_NONEXISTENT_PACKAGE   package absent on PyPI at PR creation time
  P2_INVALID_VERSION_SPEC  exact concrete ==pin had no release on/before PR time
  P3_DIRECT_KNOWN_VULNERABILITY  advisory published on/before PR time covers pin
  NONE

Secondary label (most relevant, else NONE):
  S4_LICENSE_POLICY_CONFLICT  copyleft license (GPL/AGPL/LGPL family)
  S7_METADATA_MISSING         exists but no usable license metadata
  S8_EVIDENCE_UNRESOLVED      could not reach PyPI/OSV or could not time-align
  NONE

Only change_type in {add, version_change} can be risky; remove => NONE/NONE.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

# ``packaging`` is a general-purpose library (PyPI's own version-parsing lib),
# not a pipeline module, so using it does not break the independence constraint.
from packaging.version import InvalidVersion, Version

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_PATCHES = os.path.join(
    REPO_ROOT, "outputs", "tse_gap_closure", "data", "dependency_change_patches.jsonl"
)
DEFAULT_OUT = os.path.join(
    REPO_ROOT, "outputs", "tse_gap_closure", "data", "labels_B.csv"
)
DEFAULT_CACHE = os.path.join(
    REPO_ROOT, "outputs", "tse_gap_closure", "data", "labeler_b_cache"
)

PYPI_URL = "https://pypi.org/pypi/{name}/json"
OSV_URL = "https://api.osv.dev/v1/query"
USER_AGENT = "AgentSupplyGuard-labeler_B/1.0 (independent dependency-risk study)"
HTTP_TIMEOUT = 30
HTTP_RETRIES = 3

COPYLEFT_TOKENS = ("gpl", "agpl", "lgpl", "gnu general public", "gnu lesser", "gnu affero")

# Global counters for live-vs-cache reporting (guarded by a lock).
_stats_lock = threading.Lock()
_FETCH_STATS = Counter()


# --------------------------------------------------------------------------- #
# Time helpers (own implementation)
# --------------------------------------------------------------------------- #
def parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    # Normalize trailing Z and bare offsets to something fromisoformat eats.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # Fallback for formats like '2021-01-01T00:00:00' with fractional secs.
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# --------------------------------------------------------------------------- #
# HTTP + cache layer (own implementation)
# --------------------------------------------------------------------------- #
def _cache_paths(cache_dir: str) -> Tuple[str, str]:
    pypi_dir = os.path.join(cache_dir, "pypi")
    osv_dir = os.path.join(cache_dir, "osv")
    os.makedirs(pypi_dir, exist_ok=True)
    os.makedirs(osv_dir, exist_ok=True)
    return pypi_dir, osv_dir


def _safe_name(name: str) -> str:
    """Filesystem-safe cache key for a package name."""
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in name) or "_empty_"


def _read_cache(path: str) -> Optional[dict]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _write_cache(path: str, obj: dict) -> None:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        os.replace(tmp, path)
    except OSError:
        # Cache write failure is non-fatal.
        try:
            os.remove(tmp)
        except OSError:
            pass


def _http_get(url: str) -> Tuple[int, Optional[dict]]:
    """GET JSON. Returns (status, parsed_json_or_None)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    last_exc = None
    for attempt in range(HTTP_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                data = resp.read()
                return resp.getcode(), json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, None
            last_exc = e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            last_exc = e
    raise RuntimeError(f"GET {url} failed: {type(last_exc).__name__}: {last_exc}")


def _http_post_json(url: str, body: dict) -> Tuple[int, Optional[dict]]:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/json"},
    )
    last_exc = None
    for attempt in range(HTTP_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                data = resp.read()
                return resp.getcode(), json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_exc = e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            last_exc = e
    raise RuntimeError(f"POST {url} failed: {type(last_exc).__name__}: {last_exc}")


def fetch_pypi(name: str, cache_dir: str) -> dict:
    """Fetch (or read cached) PyPI JSON metadata for a normalized package name.

    Returns a wrapper dict: {"status": int, "data": <pypi json or None>,
    "error": <str or None>}. status 404 => package absent now.
    """
    pypi_dir, _ = _cache_paths(cache_dir)
    cache_path = os.path.join(pypi_dir, _safe_name(name) + ".json")
    cached = _read_cache(cache_path)
    if cached is not None:
        with _stats_lock:
            _FETCH_STATS["pypi_cached"] += 1
        return cached
    try:
        status, data = _http_get(PYPI_URL.format(name=urllib.parse.quote(name, safe="")))
        result = {"status": status, "data": data, "error": None}
    except RuntimeError as e:
        result = {"status": None, "data": None, "error": str(e)}
    # Cache successful HTTP outcomes (incl. 404) but not transient network errors.
    if result["error"] is None:
        _write_cache(cache_path, result)
    with _stats_lock:
        _FETCH_STATS["pypi_live"] += 1
    return result


def fetch_osv(name: str, cache_dir: str) -> dict:
    """Fetch (or read cached) OSV advisories for a normalized package name."""
    _, osv_dir = _cache_paths(cache_dir)
    cache_path = os.path.join(osv_dir, _safe_name(name) + ".json")
    cached = _read_cache(cache_path)
    if cached is not None:
        with _stats_lock:
            _FETCH_STATS["osv_cached"] += 1
        return cached
    try:
        status, data = _http_post_json(OSV_URL, {"package": {"name": name, "ecosystem": "PyPI"}})
        result = {"status": status, "data": data, "error": None}
    except RuntimeError as e:
        result = {"status": None, "data": None, "error": str(e)}
    if result["error"] is None:
        _write_cache(cache_path, result)
    with _stats_lock:
        _FETCH_STATS["osv_live"] += 1
    return result


# --------------------------------------------------------------------------- #
# PyPI parsing (own implementation)
# --------------------------------------------------------------------------- #
def pypi_release_earliest_upload(files: List[dict]) -> Optional[datetime]:
    """Earliest file upload_time across the files of one release version."""
    best: Optional[datetime] = None
    for f in files or []:
        ts = parse_ts(f.get("upload_time_iso_8601") or f.get("upload_time"))
        if ts is None:
            continue
        if best is None or ts < best:
            best = ts
    return best


def package_earliest_upload(pypi_data: dict) -> Optional[datetime]:
    """Earliest release upload_time across ALL versions of the package."""
    releases = (pypi_data or {}).get("releases") or {}
    best: Optional[datetime] = None
    for _ver, files in releases.items():
        e = pypi_release_earliest_upload(files)
        if e is None:
            continue
        if best is None or e < best:
            best = e
    return best


def version_upload_time(pypi_data: dict, version_str: str) -> Tuple[bool, Optional[datetime]]:
    """For a concrete version string, return (release_present_in_index, earliest_upload).

    Matching is done on PEP 440 canonical version equality so that e.g.
    '2.0' and '2.0.0' compare equal, and pre/post markers are respected.
    release_present_in_index is True iff a key for that version exists in the
    releases map at all (even if it has no usable timestamps).
    """
    releases = (pypi_data or {}).get("releases") or {}
    try:
        target = Version(version_str)
    except InvalidVersion:
        target = None

    # First try exact string key (fast path).
    if version_str in releases:
        return True, pypi_release_earliest_upload(releases[version_str])

    # Fall back to canonical-version equality.
    if target is not None:
        for key, files in releases.items():
            try:
                if Version(key) == target:
                    return True, pypi_release_earliest_upload(files)
            except InvalidVersion:
                continue
    return False, None


def has_license_metadata(pypi_data: dict) -> Tuple[bool, str]:
    """Return (has_usable_license, copyleft_flag_or_empty).

    copyleft tag is non-empty iff a GPL/AGPL/LGPL-family token is found.
    """
    info = (pypi_data or {}).get("info") or {}
    lic = (info.get("license") or "").strip()
    classifiers = info.get("classifiers") or []
    # Newer metadata may carry SPDX expression in license_expression.
    lic_expr = (info.get("license_expression") or "").strip()

    license_classifiers = [c for c in classifiers if isinstance(c, str) and c.startswith("License ::")]

    haystack_parts = [lic.lower(), lic_expr.lower()] + [c.lower() for c in license_classifiers]
    haystack = " ".join(haystack_parts)

    copyleft = ""
    for tok in COPYLEFT_TOKENS:
        if tok in haystack:
            copyleft = tok
            break

    # "Usable" license metadata: a non-empty license string/expression, OR a
    # License classifier that is more specific than the bare "License ::" /
    # "License :: OSI Approved" umbrella.
    usable = False
    if lic or lic_expr:
        usable = True
    else:
        for c in license_classifiers:
            tail = c.split("::")[-1].strip().lower()
            if tail and tail not in ("osi approved",):
                usable = True
                break
    return usable, copyleft


# --------------------------------------------------------------------------- #
# OSV parsing + PEP 440 range logic (own implementation)
# --------------------------------------------------------------------------- #
def _coerce_version(v: str) -> Optional[Version]:
    try:
        return Version(v)
    except InvalidVersion:
        return None


def range_covers(events: List[dict], target: Version) -> bool:
    """Decide whether a target version falls inside an OSV ECOSYSTEM/SEMVER range.

    OSV ranges are an ordered event stream of introduced / fixed /
    last_affected markers. We sort the boundary versions and sweep: a version
    is affected once an 'introduced' boundary <= it has occurred and no later
    'fixed' (exclusive) or 'last_affected' (inclusive) boundary has closed it.
    'introduced':'0' means "from the beginning".
    """
    # Build (version_or_None, kind) boundaries. None sorts as -inf for '0'.
    boundaries: List[Tuple[Optional[Version], str]] = []
    for ev in events or []:
        if "introduced" in ev:
            raw = ev["introduced"]
            if raw == "0":
                boundaries.append((None, "introduced"))
            else:
                ver = _coerce_version(raw)
                if ver is not None:
                    boundaries.append((ver, "introduced"))
        elif "fixed" in ev:
            ver = _coerce_version(ev["fixed"])
            if ver is not None:
                boundaries.append((ver, "fixed"))
        elif "last_affected" in ev:
            ver = _coerce_version(ev["last_affected"])
            if ver is not None:
                boundaries.append((ver, "last_affected"))
        # 'limit' events are ignored for affected-determination.

    if not boundaries:
        return False

    # Sort: 'introduced':'0' (None) first; otherwise by version. For ties at the
    # same version, process 'introduced' before close events so a same-version
    # fixed correctly excludes.
    def sort_key(b: Tuple[Optional[Version], str]):
        ver, kind = b
        order = {"introduced": 0, "last_affected": 1, "fixed": 2}.get(kind, 3)
        # None (introduced '0') is the smallest.
        return (0 if ver is None else 1, ver if ver is not None else Version("0"), order)

    boundaries.sort(key=sort_key)

    affected = False
    for ver, kind in boundaries:
        if kind == "introduced":
            if ver is None or target >= ver:
                affected = True
            # introduced strictly above target: cannot affect from here under
            # this sweep, but a later introduced could still match — keep going.
        elif kind == "fixed":
            # Fixed is exclusive: versions >= fixed are not affected by this seg.
            if target >= ver:
                affected = False
        elif kind == "last_affected":
            # Inclusive upper bound: versions > last_affected are not affected.
            if target > ver:
                affected = False
    return affected


def advisory_covers_version(vuln: dict, normalized: str, target: Version) -> bool:
    """Does this OSV vuln cover `target` for our PyPI package?"""
    for aff in vuln.get("affected") or []:
        pkg = aff.get("package") or {}
        eco = (pkg.get("ecosystem") or "").lower()
        pname = (pkg.get("name") or "").lower()
        if eco and eco != "pypi":
            continue
        # Be lenient on name match (OSV uses canonical PyPI names too).
        if pname and pname != normalized.lower():
            # normalize hyphen/underscore/dot differences
            def norm(x: str) -> str:
                return x.replace("_", "-").replace(".", "-").lower()
            if norm(pname) != norm(normalized):
                continue

        # Explicit affected versions list.
        versions = aff.get("versions") or []
        for v in versions:
            cv = _coerce_version(v)
            if cv is not None and cv == target:
                return True
            if v == str(target):
                return True

        # Range events.
        for rg in aff.get("ranges") or []:
            rtype = (rg.get("type") or "").upper()
            if rtype in ("ECOSYSTEM", "SEMVER"):
                if range_covers(rg.get("events") or [], target):
                    return True
            # GIT ranges are not version-resolvable for PyPI; skip.
    return False


def known_vuln_at_time(
    osv_data: dict, normalized: str, target: Version, created_at: datetime
) -> Tuple[bool, List[str]]:
    """Return (is_vulnerable, [advisory_ids]) for advisories published on/before
    `created_at` that cover `target`."""
    hits: List[str] = []
    vulns = (osv_data or {}).get("vulns") or []
    for v in vulns:
        published = parse_ts(v.get("published"))
        if published is None:
            # Without a publish time we cannot assert it was KNOWN at PR time.
            continue
        if published > created_at:
            continue
        if advisory_covers_version(v, normalized, target):
            hits.append(v.get("id") or "?")
    return (len(hits) > 0, hits)


# --------------------------------------------------------------------------- #
# Per-package evidence assembly
# --------------------------------------------------------------------------- #
def gather_package_evidence(normalized: str, cache_dir: str) -> dict:
    """Fetch PyPI + OSV once per unique package; return a compact evidence dict."""
    pypi = fetch_pypi(normalized, cache_dir)
    osv = fetch_osv(normalized, cache_dir)
    return {"pypi": pypi, "osv": osv}


# --------------------------------------------------------------------------- #
# Labeling (own implementation of the rules)
# --------------------------------------------------------------------------- #
def label_row(row: dict, evidence: dict) -> Dict[str, str]:
    change_type = (row.get("change_type") or "").strip()
    normalized = row.get("normalized_package_name") or row.get("package_name") or ""
    version_pin = row.get("version_pin")
    specifier_raw = row.get("specifier_raw") or ""
    created_at = parse_ts(row.get("created_at"))

    primary = "NONE"
    secondary = "NONE"
    confidence = "high"
    note_bits: List[str] = []

    pypi = evidence["pypi"]
    osv = evidence["osv"]

    # ----- remove can never be risky -----
    if change_type == "remove":
        return _mk(row, "NONE", "NONE", "high", "change_type=remove; not risk-bearing")

    # ----- evidence reachability -----
    pypi_unreachable = pypi.get("error") is not None or (
        pypi.get("status") is None and pypi.get("data") is None
    )
    osv_unreachable = osv.get("error") is not None

    if created_at is None:
        # Cannot time-align at all.
        return _mk(
            row, "NONE", "S8_EVIDENCE_UNRESOLVED", "low",
            "missing/unparseable created_at; cannot time-align",
        )

    pypi_status = pypi.get("status")
    pypi_data = pypi.get("data")

    # ===================================================================== #
    # PRIMARY LABEL
    # ===================================================================== #
    # ---- P1: package nonexistent at PR creation time ----
    pkg_earliest: Optional[datetime] = None
    if pypi_status == 404:
        primary = "P1_NONEXISTENT_PACKAGE"
        note_bits.append("PyPI 404: package absent now")
        confidence = "high"
    elif pypi_unreachable or pypi_data is None:
        # Could not determine existence -> do NOT label P1.
        secondary = "S8_EVIDENCE_UNRESOLVED"
        confidence = "low"
        note_bits.append("PyPI unreachable; existence undetermined")
        return _mk(row, "NONE", secondary, confidence, "; ".join(note_bits))
    else:
        pkg_earliest = package_earliest_upload(pypi_data)
        if pkg_earliest is None:
            # Package exists in index but no usable timestamps anywhere ->
            # cannot assert it post-dates the PR; do NOT label P1.
            note_bits.append("no upload timestamps on PyPI; P1 indeterminate")
            confidence = "low"
        elif pkg_earliest > created_at:
            primary = "P1_NONEXISTENT_PACKAGE"
            note_bits.append(
                f"earliest release {pkg_earliest.date()} > PR {created_at.date()}"
            )
            confidence = "high"

    # ---- P2: invalid version spec (concrete ==pin not yet released) ----
    if primary == "NONE":
        is_concrete_pin = bool(version_pin) and isinstance(version_pin, str) and version_pin.strip() != ""
        # version_pin in this corpus is the resolved concrete == version (or None).
        if is_concrete_pin:
            present, vtime = version_upload_time(pypi_data, version_pin.strip())
            if not present:
                # That exact version key does not exist in the index now.
                primary = "P2_INVALID_VERSION_SPEC"
                note_bits.append(f"pin =={version_pin} not present on PyPI")
                confidence = "high"
            elif vtime is None:
                # Version key exists but no timestamp -> indeterminate on timing.
                note_bits.append(f"pin =={version_pin} present but no upload time")
                confidence = "medium" if confidence == "high" else confidence
            elif vtime > created_at:
                primary = "P2_INVALID_VERSION_SPEC"
                note_bits.append(
                    f"pin =={version_pin} uploaded {vtime.date()} > PR {created_at.date()}"
                )
                confidence = "high"
        # Range / unpinned -> never P2.

    # ---- P3: direct known vulnerability covering the pin ----
    if primary == "NONE":
        # P3 requires a concrete version to check coverage against.
        concrete_ver: Optional[Version] = None
        if version_pin and isinstance(version_pin, str) and version_pin.strip():
            concrete_ver = _coerce_version(version_pin.strip())
        if concrete_ver is not None:
            if osv_unreachable or osv.get("data") is None:
                if secondary == "NONE":
                    secondary = "S8_EVIDENCE_UNRESOLVED"
                note_bits.append("OSV unreachable; P3 undetermined")
                confidence = "low"
            else:
                vuln, ids = known_vuln_at_time(osv["data"], normalized, concrete_ver, created_at)
                if vuln:
                    primary = "P3_DIRECT_KNOWN_VULNERABILITY"
                    shown = ",".join(ids[:3]) + ("..." if len(ids) > 3 else "")
                    note_bits.append(f"advisory(ies) known at PR time cover =={version_pin}: {shown}")
                    confidence = "high"
        # No concrete version (range/unpinned) -> we do not attribute P3 to a
        # specific pinned version per the rules.

    # ===================================================================== #
    # SECONDARY LABEL (only meaningfully set when not already S8 and pkg known)
    # ===================================================================== #
    if secondary == "NONE" and pypi_data is not None and pypi_status != 404:
        usable, copyleft = has_license_metadata(pypi_data)
        if copyleft:
            secondary = "S4_LICENSE_POLICY_CONFLICT"
            note_bits.append(f"copyleft license token '{copyleft}'")
        elif not usable:
            secondary = "S7_METADATA_MISSING"
            note_bits.append("no usable license metadata")

    # Confidence floor: if we never resolved a concrete timestamp for the
    # relevant artifact and primary is NONE, drop to medium at best for adds
    # with no pin (we only validated existence).
    if primary == "NONE" and confidence == "high":
        if not (version_pin and isinstance(version_pin, str) and version_pin.strip()):
            # range/unpinned add: we did time-align package existence (high) if
            # pkg_earliest known; otherwise medium.
            if pkg_earliest is None:
                confidence = "medium"

    note = "; ".join(note_bits) if note_bits else "no risk evidence found"
    return _mk(row, primary, secondary, confidence, note)


def _mk(row: dict, primary: str, secondary: str, confidence: str, note: str) -> Dict[str, str]:
    return {
        "change_id": row.get("change_id", ""),
        "pr_id": row.get("pr_id", ""),
        "repo": row.get("repo_full_name", ""),
        "created_at": row.get("created_at", ""),
        "package_name": row.get("package_name", ""),
        "pinned_version": row.get("version_pin") or "",
        "change_type": row.get("change_type", ""),
        "label_primary": primary,
        "label_secondary": secondary,
        "label_confidence": confidence,
        "evidence_source": "live_pypi_osv(labeler_B)",
        "evidence_note": note[:300],
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def load_rows(path: str) -> List[dict]:
    rows: List[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="labeler_B: independent dependency-risk labeler")
    ap.add_argument("--patches", default=DEFAULT_PATCHES)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--cache-dir", default=DEFAULT_CACHE)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args(argv)

    rows = load_rows(args.patches)
    print(f"[labeler_B] loaded {len(rows)} dependency-change rows from {args.patches}")

    # Unique packages that actually need network evidence (non-remove rows).
    needed: set = set()
    for r in rows:
        if (r.get("change_type") or "").strip() == "remove":
            continue
        name = r.get("normalized_package_name") or r.get("package_name")
        if name:
            needed.add(name)
    print(f"[labeler_B] {len(needed)} unique packages need evidence (of {len(rows)} rows)")

    os.makedirs(args.cache_dir, exist_ok=True)
    evidence_by_pkg: Dict[str, dict] = {}

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(gather_package_evidence, name, args.cache_dir): name for name in needed}
        done = 0
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                evidence_by_pkg[name] = fut.result()
            except Exception as e:  # defensive: keep going
                evidence_by_pkg[name] = {
                    "pypi": {"status": None, "data": None, "error": f"{type(e).__name__}: {e}"},
                    "osv": {"status": None, "data": None, "error": f"{type(e).__name__}: {e}"},
                }
            done += 1
            if done % 200 == 0 or done == len(futs):
                print(f"[labeler_B] fetched evidence for {done}/{len(futs)} packages")

    # Empty/placeholder evidence for remove rows (never queried).
    empty_ev = {
        "pypi": {"status": None, "data": None, "error": None},
        "osv": {"status": None, "data": None, "error": None},
    }

    out_rows: List[Dict[str, str]] = []
    primary_counter: Counter = Counter()
    secondary_counter: Counter = Counter()
    conf_counter: Counter = Counter()
    for r in rows:
        name = r.get("normalized_package_name") or r.get("package_name")
        ev = evidence_by_pkg.get(name, empty_ev)
        labeled = label_row(r, ev)
        out_rows.append(labeled)
        primary_counter[labeled["label_primary"]] += 1
        secondary_counter[labeled["label_secondary"]] += 1
        conf_counter[labeled["label_confidence"]] += 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    fieldnames = [
        "change_id", "pr_id", "repo", "created_at", "package_name", "pinned_version",
        "change_type", "label_primary", "label_secondary", "label_confidence",
        "evidence_source", "evidence_note",
    ]
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        for orow in out_rows:
            w.writerow(orow)

    # ----- report -----
    print(f"\n[labeler_B] wrote {len(out_rows)} rows -> {args.out}")
    print(f"[labeler_B] CSV row count check: {len(out_rows)} (expected {len(rows)})")
    print(f"[labeler_B] primary-label distribution: {dict(primary_counter)}")
    print(f"[labeler_B] secondary-label distribution: {dict(secondary_counter)}")
    print(f"[labeler_B] confidence distribution: {dict(conf_counter)}")
    with _stats_lock:
        stats = dict(_FETCH_STATS)
    print(f"[labeler_B] fetch stats: {stats}")
    pypi_live = stats.get("pypi_live", 0)
    pypi_cached = stats.get("pypi_cached", 0)
    osv_live = stats.get("osv_live", 0)
    osv_cached = stats.get("osv_cached", 0)
    print(
        f"[labeler_B] PyPI: {pypi_live} live / {pypi_cached} cached | "
        f"OSV: {osv_live} live / {osv_cached} cached"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

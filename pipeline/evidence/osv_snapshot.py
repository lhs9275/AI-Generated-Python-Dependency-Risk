"""OSV advisory snapshot: was a published advisory affecting <version> known at PR time?

Pure functions operate on an OSV query response
(POST https://api.osv.dev/v1/query {"package":{"name","ecosystem":"PyPI"}}).
Tested against frozen fixtures; no network.

C.5 rule: an advisory counts for a deterministic S3 positive only if it was
*published at or before* the PR time AND the version is in its affected range.
Advisories found only by a live "now" query (no usable published date placing
them before PR time) must not feed prevalence claims -- that gating lives in
reconstruct_historical_evidence.derive_risk_labels via evidence_source.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from packaging.version import Version, InvalidVersion

OSV_URL = "https://api.osv.dev/v1/query"


def _dt(s):
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


def _v(s):
    try:
        return Version(str(s))
    except (InvalidVersion, TypeError):
        return None


def version_in_range(affected: dict, version: str) -> bool:
    """True if `version` falls in this OSV `affected` entry (explicit list or ranges)."""
    explicit = affected.get("versions")
    if explicit:
        return version in explicit
    target = _v(version)
    if target is None:
        return False
    for rng in affected.get("ranges", []) or []:
        if rng.get("type") not in ("ECOSYSTEM", "SEMVER", None):
            continue
        # Pair events into disjoint [introduced, fixed) / [introduced, last_affected]
        # intervals. A range may hold several such branches (e.g. one per release
        # line); the version is affected if it falls in ANY branch. A linear toggle
        # is wrong here: a later branch's 'fixed' must not clear an earlier match.
        lo = None
        open_interval = False
        for ev in rng.get("events", []) or []:
            if "introduced" in ev:
                intro = ev["introduced"]
                lo = None if intro in ("0", 0) else _v(intro)
                open_interval = True
            elif "fixed" in ev and open_interval:
                hi = _v(ev["fixed"])
                if (lo is None or target >= lo) and (hi is None or target < hi):
                    return True
                open_interval = False
            elif "last_affected" in ev and open_interval:
                hi = _v(ev["last_affected"])
                if (lo is None or target >= lo) and (hi is None or target <= hi):
                    return True
                open_interval = False
        if open_interval and (lo is None or target >= lo):  # introduced, never fixed
            return True
    return False


def advisory_facts(osv_json: dict, version: str, pr_time: str) -> dict:
    """Advisories known at pr_time affecting `version` (published <= pr_time, in range)."""
    pdt = _dt(pr_time)
    ids, ranges, published = [], [], []
    for vuln in (osv_json or {}).get("vulns", []) or []:
        pub = vuln.get("published")
        pub_dt = _dt(pub)
        in_range = any(version_in_range(a, version) for a in vuln.get("affected", []) or [])
        if not in_range:
            continue
        # Known at PR time only if published on/before pr_time.
        if pub_dt is not None and pdt is not None and pub_dt <= pdt:
            ids.append(vuln.get("id"))
            published.append(pub)
            for a in vuln.get("affected", []) or []:
                if version_in_range(a, version) and a.get("ranges"):
                    ranges.append(a["ranges"])
                    break
    return {
        "direct_advisory_known_at_pr_time": bool(ids),
        "direct_advisory_ids": ids,
        "advisory_published_at": min(published, key=lambda p: _dt(p)) if published else None,
        "affected_range": json.dumps(ranges[0]) if ranges else None,
    }


def fetch_osv(name: str, cache_dir: Path, fetcher=None, pause: float = 0.0):
    """Fetch + cache OSV advisories for a package (all versions). Returns dict."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{name}.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except json.JSONDecodeError:
            pass
    if fetcher is None:
        fetcher = _default_fetch
    data = fetcher(name)
    cache.write_text(json.dumps(data) if data is not None else "{}")
    if pause:
        time.sleep(pause)
    return data or {}


def _default_fetch(name):
    body = json.dumps({"package": {"name": name, "ecosystem": "PyPI"}}).encode()
    req = urllib.request.Request(OSV_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError):
        return {}

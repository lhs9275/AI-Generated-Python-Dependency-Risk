"""PyPI release-metadata snapshot: existence/version/yank facts at a PR time.

Network fetching is optional and injected; the pure functions here operate on
already-fetched PyPI JSON (https://pypi.org/pypi/<name>/json), so they are tested
against frozen fixtures with no network.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

PYPI_URL = "https://pypi.org/pypi/{name}/json"


def _dt(s):
    """Parse an ISO-8601 timestamp (with optional trailing Z) to aware datetime."""
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        try:
            d = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def parse_pypi(j: dict) -> dict:
    """Reduce PyPI JSON to {package_created_at, exists, versions:{ver:{upload_time,yanked}}}."""
    releases = j.get("releases", {}) or {}
    versions = {}
    all_uploads = []
    for ver, files in releases.items():
        uploads = [f.get("upload_time_iso_8601") or f.get("upload_time")
                   for f in (files or []) if f.get("upload_time_iso_8601") or f.get("upload_time")]
        uploads = [u for u in uploads if u]
        earliest = min(uploads, key=lambda u: _dt(u) or datetime.max.replace(tzinfo=timezone.utc)) if uploads else None
        yanked = bool(files) and all(f.get("yanked") for f in files)
        versions[ver] = {"version_upload_time": earliest, "yanked": yanked}
        all_uploads.extend(uploads)
    created = min(all_uploads, key=lambda u: _dt(u) or datetime.max.replace(tzinfo=timezone.utc)) if all_uploads else None
    exists = bool(j.get("info")) or bool(releases)
    return {"package_created_at": created, "exists": exists, "versions": versions}


def package_exists_at(facts: dict, pr_time: str):
    """True/False if package existed at pr_time; None if creation time unknown."""
    created = facts.get("package_created_at")
    if not created:
        return None if not facts.get("exists") else None
    cdt, pdt = _dt(created), _dt(pr_time)
    if cdt is None or pdt is None:
        return None
    return cdt <= pdt


def version_facts_at(facts: dict, version: str, pr_time: str) -> dict:
    """Existence/upload/yank facts for a specific version at pr_time."""
    v = facts.get("versions", {}).get(version)
    if not v:
        return {"version_exists_at_pr_time": False, "version_upload_time": None,
                "version_yanked_at_pr_time": None}
    upload = v.get("version_upload_time")
    udt, pdt = _dt(upload), _dt(pr_time)
    exists = bool(upload) and udt is not None and pdt is not None and udt <= pdt
    return {"version_exists_at_pr_time": exists,
            "version_upload_time": upload,
            "version_yanked_at_pr_time": v.get("yanked")}


def fetch_pypi(name: str, cache_dir: Path, fetcher=None, pause: float = 0.0):
    """Fetch + cache raw PyPI JSON for a package. Returns dict or None (404/error)."""
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
    data = fetcher(PYPI_URL.format(name=name))
    cache.write_text(json.dumps(data) if data is not None else "null")
    if pause:
        time.sleep(pause)
    return data


def _default_fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except (urllib.error.URLError, TimeoutError):
        return None

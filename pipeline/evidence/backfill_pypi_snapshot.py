"""Explicit PyPI snapshot backfill for frozen S1 evidence.

This tool is intentionally outside the guard path. It can apply previously
collected fact rows offline, or collect PyPI JSON only when --allow-network is
provided explicitly.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from pipeline.audit_evidence_coverage import normalize_package
from pipeline.evidence.license_snapshot import license_from_pypi
from pipeline.evidence.pypi_snapshot import PYPI_URL, parse_pypi


BACKFILL_REASON = "canonical_missing_snapshot"
FACT_FIELDS = [
    "evidence_refs_path",
    "package_normalized",
    "snapshot_key",
    "exists",
    "known_versions",
    "latest_version",
    "retrieved_at",
    "source_url",
    "source_sha256",
    "license",
]
_CACHE_MISS = object()


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _source_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _cache_path(cache_dir: Path, package_normalized: str) -> Path:
    return Path(cache_dir) / f"{package_normalized}.json"


def _read_status_cache(path: Path) -> dict | None | object:
    if not path.exists():
        return _CACHE_MISS

    value = json.loads(path.read_text(encoding="utf-8"))
    if value is None:
        raise RuntimeError(f"unproven null cache entry cannot establish package absence: {path}")

    if isinstance(value, dict) and "status" in value:
        status = int(value["status"])
        if status == 404:
            return None
        if status == 200:
            data = value.get("data")
            if not isinstance(data, dict):
                raise RuntimeError(f"status-aware PyPI cache has invalid 200 payload: {path}")
            return data
        raise RuntimeError(f"unsupported PyPI cache status {status}: {path}")

    if isinstance(value, dict):
        return value

    raise RuntimeError(f"unsupported PyPI cache payload: {path}")


def _strict_fetch_pypi_url(url: str) -> dict | None:
    """Fetch PyPI JSON, treating only HTTP 404 as package absence."""
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _fetch_with_status(url: str, fetcher) -> tuple[int, dict | None]:
    try:
        data = fetcher(url)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return 404, None
        raise

    if data is None:
        return 404, None
    if not isinstance(data, dict):
        raise RuntimeError(f"PyPI fetcher returned unsupported payload for {url}: {type(data).__name__}")
    return 200, data


def _fetch_pypi_backfill(package_normalized: str, cache_dir: Path, fetcher=None) -> dict | None:
    """Fetch PyPI JSON using a status-aware cache.

    Legacy raw JSON caches are accepted as proven 200 responses. Legacy raw
    null caches are rejected because they do not distinguish a real HTTP 404
    from a transient network failure swallowed by older helpers.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(cache_dir, package_normalized)
    cached = _read_status_cache(cache)
    if cached is not _CACHE_MISS:
        return cached

    url = PYPI_URL.format(name=package_normalized)
    status, data = _fetch_with_status(url, fetcher or _strict_fetch_pypi_url)
    cache.write_text(
        json.dumps({"data": data, "status": status, "url": url}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return data


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def _parse_exists(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValueError(f"invalid exists value in backfill facts: {value!r}")


def _parse_known_versions(value: object) -> list[str]:
    if isinstance(value, list):
        return sorted(str(item) for item in value)
    if value in (None, ""):
        return []
    parsed = json.loads(str(value))
    if not isinstance(parsed, list):
        raise ValueError(f"known_versions must be a JSON list: {value!r}")
    return sorted(str(item) for item in parsed)


def _csv_value(field: str, value: object) -> str:
    if field == "exists":
        return "true" if value is True else "false"
    if field == "known_versions":
        return json.dumps(_parse_known_versions(value), ensure_ascii=False)
    return "" if value is None else str(value)


def _read_csv_rows(path: Path) -> list[dict]:
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _dedupe_rows(rows: Iterable[dict]) -> list[dict]:
    deduped: dict[tuple[str, str], dict] = {}
    for row in rows:
        evidence_path = str(row.get("evidence_refs_path") or "")
        package = normalize_package(str(row.get("package_normalized") or row.get("package_raw") or ""))
        snapshot_key = str(row.get("snapshot_key") or "")
        if not evidence_path or not package:
            continue
        normalized = {
            **row,
            "evidence_refs_path": evidence_path,
            "package_normalized": package,
            "snapshot_key": snapshot_key,
        }
        key = (evidence_path, package)
        if key not in deduped:
            deduped[key] = normalized
        elif snapshot_key and not deduped[key].get("snapshot_key"):
            deduped[key]["snapshot_key"] = snapshot_key
    return [deduped[key] for key in sorted(deduped)]


def _fact_sort_key(row: dict) -> tuple[str, str]:
    return (str(row.get("evidence_refs_path") or ""), str(row.get("package_normalized") or ""))


def _fact_from_pypi_json(
    evidence_refs_path: str,
    package_normalized: str,
    snapshot_key: str,
    pypi_json: dict | None,
    retrieved_at: str,
) -> dict:
    source_url = PYPI_URL.format(name=package_normalized)
    if pypi_json is None:
        return {
            "evidence_refs_path": evidence_refs_path,
            "package_normalized": package_normalized,
            "snapshot_key": snapshot_key,
            "exists": False,
            "known_versions": [],
            "latest_version": "",
            "retrieved_at": retrieved_at,
            "source_url": source_url,
            "source_sha256": _source_sha256(None),
            "license": "",
        }

    facts = parse_pypi(pypi_json)
    known_versions = sorted(str(version) for version in facts.get("versions", {}))
    info = pypi_json.get("info", {}) or {}
    license_value, license_missing = license_from_pypi(pypi_json)
    return {
        "evidence_refs_path": evidence_refs_path,
        "package_normalized": package_normalized,
        "snapshot_key": snapshot_key,
        "exists": bool(facts.get("exists")),
        "known_versions": known_versions,
        "latest_version": str(info.get("version") or ""),
        "retrieved_at": retrieved_at,
        "source_url": source_url,
        "source_sha256": _source_sha256(pypi_json),
        "license": "" if license_missing else str(license_value),
    }


def collect_backfill_facts(
    audit_rows: Iterable[dict],
    *,
    cache_dir: Path,
    retrieved_at: str | None = None,
    fetcher=None,
) -> list[dict]:
    """Fetch PyPI JSON for unique audit row pairs and return fact rows."""
    retrieved = retrieved_at or _utc_now()
    facts = []
    package_cache: dict[str, dict | None] = {}

    for row in _dedupe_rows(audit_rows):
        if _truthy(row.get("stdlib")) or _truthy(row.get("present")):
            continue
        package = str(row["package_normalized"])
        if package not in package_cache:
            package_cache[package] = _fetch_pypi_backfill(package, Path(cache_dir), fetcher=fetcher)
        facts.append(
            _fact_from_pypi_json(
                str(row["evidence_refs_path"]),
                package,
                str(row.get("snapshot_key") or ""),
                package_cache[package],
                retrieved,
            )
        )

    return sorted(facts, key=_fact_sort_key)


def write_facts_csv(rows: Iterable[dict], path: Path) -> None:
    """Write fact rows as a deterministic CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = _dedupe_rows(rows)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FACT_FIELDS)
        writer.writeheader()
        for row in sorted(rows, key=_fact_sort_key):
            writer.writerow({field: _csv_value(field, row.get(field, "")) for field in FACT_FIELDS})


def _entry_from_fact(row: dict) -> dict:
    entry = {
        "exists": _parse_exists(row.get("exists")),
        "known_versions": _parse_known_versions(row.get("known_versions")),
        "latest_version": str(row.get("latest_version") or ""),
        "backfill_reason": BACKFILL_REASON,
        "retrieved_at": str(row.get("retrieved_at") or ""),
        "source_url": str(row.get("source_url") or ""),
        "source_sha256": str(row.get("source_sha256") or ""),
    }
    license_value = str(row.get("license") or "").strip()
    if license_value:
        entry["license"] = license_value
    return entry


def apply_backfill_rows(rows: Iterable[dict]) -> None:
    """Apply fact rows to evidence_refs.json files deterministically."""
    grouped: dict[str, list[dict]] = {}
    for row in _dedupe_rows(rows):
        grouped.setdefault(str(row["evidence_refs_path"]), []).append(row)

    for evidence_path in sorted(grouped):
        path = Path(evidence_path)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        pypi_packages = data.setdefault("pypi_packages", {})
        if not isinstance(pypi_packages, dict):
            raise ValueError(f"pypi_packages must be an object in {path}")

        for row in sorted(grouped[evidence_path], key=_fact_sort_key):
            package = normalize_package(str(row["package_normalized"]))
            for existing_key in sorted(list(pypi_packages)):
                if normalize_package(str(existing_key)) == package:
                    del pypi_packages[existing_key]
            pypi_packages[package] = _entry_from_fact(row)

        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill frozen PyPI package-existence evidence from explicit facts.",
    )
    parser.add_argument("--audit-csv", type=Path)
    parser.add_argument("--facts-out", type=Path)
    parser.add_argument("--from-facts", type=Path)
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=Path("results/evidence_coverage/pypi_cache"))
    parser.add_argument("--retrieved-at")
    return parser


def main(argv: list[str] | None = None, *, fetcher=None):
    args = build_arg_parser().parse_args(argv)

    if args.from_facts:
        rows = _read_csv_rows(args.from_facts)
        apply_backfill_rows(rows)
        return rows

    if args.audit_csv and not args.allow_network:
        raise SystemExit("--audit-csv requires --allow-network, or use --from-facts for offline apply")
    if args.allow_network and not args.audit_csv:
        raise SystemExit("--allow-network requires --audit-csv")
    if args.allow_network and not args.facts_out:
        raise SystemExit("--facts-out is required with --allow-network --audit-csv")
    if not args.audit_csv:
        raise SystemExit("provide --from-facts or --allow-network --audit-csv")

    audit_rows = _read_csv_rows(args.audit_csv)
    facts = collect_backfill_facts(
        audit_rows,
        cache_dir=args.cache_dir,
        retrieved_at=args.retrieved_at,
        fetcher=fetcher,
    )
    write_facts_csv(facts, args.facts_out)
    apply_backfill_rows(facts)
    return facts


if __name__ == "__main__":
    main()

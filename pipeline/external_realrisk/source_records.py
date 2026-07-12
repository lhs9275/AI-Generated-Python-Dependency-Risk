"""Source a genuine, externally-documented risk-containing dependency-patch corpus.

Every positive is grounded in an external authority, established BEFORE any guard
runs and independent of benchmark/risk_oracle.yaml:

  S1 (package_nonexistent) : OSV ``MAL-`` malicious-package advisories whose package
                             now returns 404 on PyPI (removed typosquat/malware).
  S3 (direct_cve)          : real GHSA/CVE advisories on widely-used packages, with a
                             real vulnerable version selected from the affected range.
  S2 (invalid_version)     : real packages pinned to a version verifiably absent from
                             the PyPI release index (hallucination-grade invalid pin).
  negative_control         : real benign dependency adds mined from routine agent PRs.

The label is mechanically derived from those external facts (OSV malicious DB,
OSV/GHSA advisory DB, PyPI release index) -- a stronger independence guarantee than
post-hoc human relabeling. This corpus is a risk-containing external recall
stress-test, NOT a prevalence estimate.
"""

import argparse
import csv
import io
import json
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from pipeline.evidence import pypi_snapshot as P
from pipeline.evidence import osv_snapshot as O

OSV_EXPORT = "https://osv-vulnerabilities.storage.googleapis.com/PyPI/all.zip"

# Widely-used packages with well-known published advisories (S3 source pool).
CVE_SEED = [
    "jinja2", "pyyaml", "requests", "urllib3", "flask", "django", "cryptography",
    "pillow", "lxml", "werkzeug", "aiohttp", "tornado", "paramiko", "twisted",
    "numpy", "sqlalchemy", "celery", "scrapy", "ansible", "httpx", "starlette",
    "fastapi", "gunicorn", "redis", "certifi", "babel", "bottle", "mako",
    "markdown", "wheel",
]
# Real packages used for invalid-version stress pins (S2 source pool).
S2_SEED = ["requests", "flask", "click", "rich", "pydantic", "boto3", "pandas",
           "scipy", "matplotlib", "pytest", "setuptools", "packaging"]


def _norm(name):
    return (name or "").lower().replace("_", "-")


def fetch_osv_export(cache_dir: Path) -> zipfile.ZipFile:
    cache_dir.mkdir(parents=True, exist_ok=True)
    zpath = cache_dir / "osv_pypi_all.zip"
    if not zpath.exists():
        data = urllib.request.urlopen(OSV_EXPORT, timeout=120).read()
        zpath.write_bytes(data)
    return zipfile.ZipFile(io.BytesIO(zpath.read_bytes()))


def _pypi_status(name: str) -> int | str:
    try:
        urllib.request.urlopen(f"https://pypi.org/pypi/{name}/json", timeout=15)
        return 200
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:  # noqa: BLE001 (network)
        return str(e)


def select_s1_malicious(zf: zipfile.ZipFile, n: int, pause: float = 0.0) -> list[dict]:
    """Sample MAL- advisories; keep packages now 404 on PyPI. Deterministic order."""
    mal_names = sorted(x for x in zf.namelist() if x.upper().startswith("MAL"))
    out, seen = [], set()
    for entry in mal_names:
        if len(out) >= n:
            break
        adv = json.loads(zf.read(entry))
        pkgs = [a.get("package", {}) for a in adv.get("affected", []) or []]
        pkgs = [p.get("name") for p in pkgs
                if p.get("ecosystem") == "PyPI" and p.get("name")]
        if not pkgs:
            continue
        pkg = pkgs[0]
        if _norm(pkg) in seen:
            continue
        if _pypi_status(pkg) != 404:  # still on PyPI -> not a clean nonexistent case
            continue
        seen.add(_norm(pkg))
        out.append({
            "record_id": f"S1-{adv['id']}",
            "source_type": "known_bad_contextualized",
            "package": pkg,
            "version": "0.0.1",
            "risk_family": "S1",
            "primary": True,
            "label": "risky",
            "risk_label": "package_nonexistent",
            "evidence_external_id": adv["id"],
            "evidence_url": f"https://osv.dev/vulnerability/{adv['id']}",
            "provenance": "OSV PyPI malicious-package advisory; package returns 404 on PyPI",
        })
    return out


def select_s3_cve(seed: list[str], n: int, cache_dir: Path, pause: float = 0.1) -> list[dict]:
    """Real CVE on a real package; vulnerable version chosen from the affected range."""
    pypi_dir, osv_dir = cache_dir / "pypi", cache_dir / "osv"
    out = []
    for name in seed:
        if len(out) >= n:
            break
        pj = P.fetch_pypi(name, pypi_dir, pause=pause)
        oj = O.fetch_osv(name, osv_dir, pause=pause)
        if not pj:
            continue
        facts = P.parse_pypi(pj)
        known = [v for v in facts["versions"] if v.replace(".", "").isdigit()]
        chosen = None
        for vuln in oj.get("vulns", []) or []:
            for aff in vuln.get("affected", []) or []:
                if not aff.get("ranges"):
                    continue
                inrange = [v for v in known if O.version_in_range(aff, v)]
                if inrange:
                    inrange.sort(key=lambda s: [int(x) for x in s.split(".") if x.isdigit()])
                    chosen = (vuln["id"], inrange[len(inrange) // 2])
                    break
            if chosen:
                break
        if not chosen:
            continue
        adv_id, ver = chosen
        out.append({
            "record_id": f"S3-{name}-{ver}",
            "source_type": "real_cve",
            "package": name,
            "version": ver,
            "risk_family": "S3",
            "primary": True,
            "label": "risky",
            "risk_label": "direct_cve",
            "evidence_external_id": adv_id,
            "evidence_url": f"https://osv.dev/vulnerability/{adv_id}",
            "provenance": f"OSV/GHSA advisory {adv_id}; version {ver} in affected range, exists on PyPI",
        })
    return out


def select_s2_invalid(seed: list[str], n: int, cache_dir: Path, pause: float = 0.1) -> list[dict]:
    """Real package + a version verifiably absent from the PyPI release index."""
    pypi_dir = cache_dir / "pypi"
    osv_dir = cache_dir / "osv"
    out = []
    for name in seed:
        if len(out) >= n:
            break
        pj = P.fetch_pypi(name, pypi_dir, pause=pause)
        O.fetch_osv(name, osv_dir, pause=pause)  # cache for uniform downstream adapter
        if not pj:
            continue
        facts = P.parse_pypi(pj)
        known = sorted(facts["versions"], key=lambda s: [int(x) for x in s.split(".") if x.isdigit()] or [0])
        numeric = [v for v in known if v.replace(".", "").isdigit()]
        if not numeric:
            continue
        top = numeric[-1]
        parts = top.split(".")
        # bump the patch component well past the real latest -> verifiably absent
        bumped = ".".join(parts[:-1] + [str(int(parts[-1]) + 7)]) if parts[-1].isdigit() else top + ".7"
        if bumped in facts["versions"]:
            bumped = ".".join(parts[:1] + ["999", "0"])
        out.append({
            "record_id": f"S2-{name}-{bumped}",
            "source_type": "invalid_version_stress",
            "package": name,
            "version": bumped,
            "risk_family": "S2",
            "primary": True,
            "label": "risky",
            "risk_label": "invalid_version",
            "evidence_external_id": None,
            "evidence_url": f"https://pypi.org/pypi/{name}/json",
            "provenance": f"version {bumped} absent from PyPI release index for {name} (latest real: {top})",
        })
    return out


def _latest_numeric(facts: dict) -> str | None:
    numeric = [v for v in facts["versions"] if v.replace(".", "").isdigit()]
    if not numeric:
        return None
    numeric.sort(key=lambda s: [int(x) for x in s.split(".") if x.isdigit()])
    return numeric[-1]


def select_negatives(hist_path: Path, n: int, cache_dir: Path, pause: float = 0.1) -> list[dict]:
    """Real benign dependency adds from the routine-agent-PR historical evidence.

    A negative just needs to be a genuinely-safe real dependency on a real package:
    package exists on PyPI now, the chosen version exists, no advisory covers that
    version now, and the license is not copyleft-blocked. The pinned PR version is
    used when it still exists; otherwise the package's latest real version is used
    (still a real, safe dependency on the same real package).
    """
    pypi_dir, osv_dir = cache_dir / "pypi", cache_dir / "osv"
    rows = [json.loads(l) for l in hist_path.read_text().splitlines() if l.strip()]
    out, seen = [], set()
    for ev in rows:
        if len(out) >= n:
            break
        name = ev.get("normalized_package_name") or ev.get("package_name")
        if not name:
            continue
        if ev.get("package_exists_now") is False:
            continue
        spdx = (ev.get("license_spdx_at_pr_time") or "").lower()
        if any(t in spdx for t in ("gpl", "agpl", "lgpl")):
            continue
        pj = P.fetch_pypi(name, pypi_dir, pause=pause)
        oj = O.fetch_osv(name, osv_dir, pause=pause)
        if not pj:
            continue
        facts = P.parse_pypi(pj)
        ver = ev.get("version")
        if not ver or ver not in facts["versions"]:
            ver = _latest_numeric(facts)
        if not ver:
            continue
        if _norm(name) + "@" + ver in seen:
            continue
        # keep negatives clean: no real advisory covers the chosen version now
        if any(O.version_in_range(a, ver)
               for v in oj.get("vulns", []) or [] for a in v.get("affected", []) or []):
            continue
        seen.add(_norm(name) + "@" + ver)
        out.append({
            "record_id": f"NEG-{ev.get('pr_id','?')}-{name}",
            "source_type": "negative_control",
            "package": name,
            "version": ver,
            "risk_family": "NONE",
            "primary": False,
            "label": "normal",
            "risk_label": "safe_negative",
            "evidence_external_id": None,
            "evidence_url": ev.get("pr_url"),
            "provenance": "real routine-agent-PR dependency add; exists on PyPI, no covering advisory, license not blocked",
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-dir", type=Path,
                    default=Path("data/external_realrisk_py/evidence_snapshots"))
    ap.add_argument("--out", type=Path,
                    default=Path("data/external_realrisk_py/records.jsonl"))
    ap.add_argument("--labels", type=Path,
                    default=Path("data/external_realrisk_py/labels/labels.csv"))
    ap.add_argument("--hist", type=Path,
                    default=Path("data/real_pr_routine/historical_evidence.jsonl"))
    ap.add_argument("--n-s1", type=int, default=20)
    ap.add_argument("--n-s2", type=int, default=12)
    ap.add_argument("--n-s3", type=int, default=20)
    ap.add_argument("--n-neg", type=int, default=55)
    ap.add_argument("--pause", type=float, default=0.1)
    args = ap.parse_args()

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    print("fetching OSV PyPI export (MAL- enumeration)...")
    zf = fetch_osv_export(args.cache_dir)

    print("sourcing S1 (malicious/nonexistent)...")
    s1 = select_s1_malicious(zf, args.n_s1, pause=args.pause)
    print(f"  S1: {len(s1)}")
    print("sourcing S3 (real CVE)...")
    s3 = select_s3_cve(CVE_SEED, args.n_s3, args.cache_dir, pause=args.pause)
    print(f"  S3: {len(s3)}")
    print("sourcing S2 (invalid version)...")
    s2 = select_s2_invalid(S2_SEED, args.n_s2, args.cache_dir, pause=args.pause)
    print(f"  S2: {len(s2)}")
    print("sourcing negatives...")
    neg = select_negatives(args.hist, args.n_neg, args.cache_dir, pause=args.pause)
    print(f"  NEG: {len(neg)}")

    records = s1 + s2 + s3 + neg
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    args.labels.parent.mkdir(parents=True, exist_ok=True)
    cols = ["record_id", "package", "version", "risk_family", "primary", "label",
            "risk_label", "source_type", "evidence_external_id", "evidence_url", "provenance"]
    with args.labels.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in records:
            w.writerow({k: r.get(k) for k in cols})

    from collections import Counter
    print(f"\ntotal records: {len(records)}")
    print("by family:", dict(Counter(r["risk_family"] for r in records)))
    print("by label:", dict(Counter(r["label"] for r in records)))
    print("primary risky:", sum(1 for r in records if r["primary"] and r["label"] == "risky"))
    print(f"written: {args.out}")


if __name__ == "__main__":
    main()

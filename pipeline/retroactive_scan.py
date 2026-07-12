"""
HISTORICAL / DISABLED: this batch scanner must not be used to produce controlled
B1_scanner / B2_scanner results.

The former batch strategy:
1. 모든 result.json에서 dep_changes 수집 → 유니크 패키지 집합 추출
2. pip-audit 1회 실행 (전체 패키지 배치) → 결과 캐시
3. PyPI JSON API 1회/패키지 (캐시) → 라이선스 캐시
4. 캐시로 각 result.json에 B1_scanner/B2_scanner 추가

is invalid for a controlled comparison: it combines unrelated manifests, does not
preserve per-manifest failures, and loses package-version identity. Existing outputs
are retained only as historical artifacts and are excluded from the manuscript. A future
controlled scanner comparison must invoke the scanner per actual manifest and record
clean, input/resolution-failure, and tool-failure states separately.
"""

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

_DEFAULT_BLOCKED = {
    "gpl-2.0", "gpl-2.0-only", "gpl-2.0-or-later",
    "gpl-3.0", "gpl-3.0-only", "gpl-3.0-or-later",
    "agpl-3.0", "agpl-3.0-only", "agpl-3.0-or-later",
    "lgpl-2.1", "lgpl-2.1-only", "lgpl-2.1-or-later",
    "lgpl-3.0", "lgpl-3.0-only", "lgpl-3.0-or-later",
}


# ── Step 1: 전체 패키지 수집 ──────────────────────────────────────────────────

def collect_all_packages(result_jsons: list[Path]) -> dict[str, set[str]]:
    """
    모든 result.json에서 agent가 추가한 패키지를 수집.
    Returns: {pkg_name_lower: {new_line, ...}}
    """
    pkg_lines: dict[str, set[str]] = {}
    for p in result_jsons:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for c in (data.get("dep_changes") or []):
            if c.get("change_type") in ("added", "modified") and c.get("new_line"):
                key = c["package"].lower().replace("-", "_")
                pkg_lines.setdefault(key, set()).add(c["new_line"])
    return pkg_lines


# ── Step 2: pip-audit 배치 실행 ──────────────────────────────────────────────

def batch_pip_audit(all_lines: set[str]) -> dict[str, list[dict]]:
    raise RuntimeError(
        "Disabled invalid batch pip-audit path. Run pip-audit per actual manifest "
        "and preserve return code, stderr, failure state, and package-version output."
    )


# ── Step 3: 라이선스 캐시 (PyPI API) ─────────────────────────────────────────

def batch_fetch_licenses(pkg_names: set[str]) -> dict[str, str]:
    """
    {pkg_name_lower: license_str} 반환. PyPI JSON API 캐시.
    """
    cache: dict[str, str] = {}
    total = len(pkg_names)
    for i, pkg in enumerate(sorted(pkg_names), 1):
        if i % 20 == 0:
            print(f"  license fetch: {i}/{total}")
        try:
            url = f"https://pypi.org/pypi/{pkg}/json"
            with urllib.request.urlopen(url, timeout=8) as resp:
                info = json.loads(resp.read())["info"]
            lic = info.get("license") or "UNKNOWN"
        except Exception:
            lic = "UNKNOWN"
        cache[pkg.lower().replace("-", "_")] = lic
    print(f"  license fetch done: {total} packages")
    return cache


# ── Issue 생성 ───────────────────────────────────────────────────────────────

def _vuln_issues(pkg: str, ver: str, vulns: list[dict]) -> list[dict]:
    issues = []
    for v in vulns:
        fix_vers = v.get("fix_versions") or []
        issues.append({
            "stage": "B1_scanner",
            "package": pkg,
            "risk_label": "scanner_vulnerability",
            "severity": "critical" if fix_vers else "high",
            "reason": f"pip-audit: {v.get('id','')} affects {pkg}=={ver}. Fix in: {fix_vers}",
            "evidence_source": "pip-audit",
            "cve": v.get("id"),
            "fix_versions": fix_vers,
            "pr_time_preventable": True,
        })
    return issues


def _license_issue(pkg: str, lic_raw: str, blocked: set) -> dict | None:
    lic = lic_raw.lower()
    if lic in ("unknown", "none", ""):
        return None
    if any(b in lic for b in blocked):
        return {
            "stage": "B2_scanner",
            "package": pkg,
            "risk_label": "scanner_license_violation",
            "severity": "critical",
            "reason": f"PyPI license '{lic_raw}' matches blocked pattern.",
            "evidence_source": "pypi-api",
            "license": lic_raw,
            "pr_time_preventable": True,
        }
    return None


def _guard_result(issues: list[dict], mode: str) -> dict:
    has_crit = any(i["severity"] == "critical" for i in issues)
    has_warn = any(i["severity"] in ("high", "medium", "warn") for i in issues)
    decision = "BLOCK" if has_crit else ("WARN" if has_warn else "PASS")
    return {
        "decision": decision,
        "stages": {},
        "risk_report": issues,
        "repair_feedback": None,
        "mode": mode,
        "note": f"{mode}: scanner-based (retroactive)",
    }


# ── Step 4: result.json 업데이트 ─────────────────────────────────────────────

def update_result_json(
    path: Path,
    vuln_cache: dict[str, list[dict]],
    license_cache: dict[str, str],
    blocked: set,
    dry_run: bool,
) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return f"error:read:{e}"

    mbm = data.get("metrics_by_mode", {})
    gbm = data.get("guard_by_mode", {})
    # B2_scanner에 라이선스 이슈가 이미 있으면 완전히 스킵
    b2_rr = gbm.get("B2_scanner", {}).get("risk_report", [])
    b1_rr = gbm.get("B1_scanner", {}).get("risk_report", [])
    if "B1_scanner" in mbm and b2_rr != b1_rr:
        # B2_scanner가 B1_scanner와 다름 → 이미 라이선스 추가됨
        return "skipped"
    if "B1_scanner" in mbm and not license_cache:
        # 라이선스 조회 없이 재실행 → 스킵
        return "skipped"

    dep_changes = data.get("dep_changes") or []
    added = [c for c in dep_changes
             if c.get("change_type") in ("added", "modified") and c.get("new_line")]

    # B1_scanner가 이미 있으면 vuln 재계산 없이 기존 값 재사용
    already_b1 = "B1_scanner" in mbm
    if already_b1:
        vuln_issues = gbm.get("B1_scanner", {}).get("risk_report", [])
    else:
        vuln_issues = []
        for c in added:
            pkg = c["package"]
            pkg_key = pkg.lower().replace("-", "_")
            ver = c.get("new_line", "").split("==")[-1] if "==" in c.get("new_line", "") else ""
            vulns = vuln_cache.get(pkg_key, [])
            vuln_issues += _vuln_issues(pkg, ver, vulns)

    lic_issues: list[dict] = []
    for c in added:
        pkg = c["package"]
        pkg_key = pkg.lower().replace("-", "_")
        lic = license_cache.get(pkg_key, "UNKNOWN")
        issue = _license_issue(pkg, lic, blocked)
        if issue:
            lic_issues.append(issue)

    b1_guard = _guard_result(vuln_issues, "B1_scanner")
    b2_guard = _guard_result(vuln_issues + lic_issues, "B2_scanner")

    if dry_run:
        return f"dry:B1={b1_guard['decision']},B2={b2_guard['decision']},v={len(vuln_issues)},l={len(lic_issues)}"

    # B1/B2 deterministic 사본
    gbm = data.get("guard_by_mode", {})
    for key, det_key in (("B1", "B1_deterministic"), ("B2", "B2_deterministic")):
        if key in gbm and det_key not in gbm:
            gbm[det_key] = {**gbm[key]}
        if key in mbm and det_key not in mbm:
            mbm[det_key] = mbm[key]

    # scanner 결과 추가
    gbm["B1_scanner"] = {"decision": b1_guard["decision"],
                         "risk_report": b1_guard["risk_report"],
                         "n_issues": len(b1_guard["risk_report"])}
    gbm["B2_scanner"] = {"decision": b2_guard["decision"],
                         "risk_report": b2_guard["risk_report"],
                         "n_issues": len(b2_guard["risk_report"])}
    data["guard_by_mode"] = gbm

    adj = data.get("adjudication", {})
    func_r = adj.get("functional")
    safety_r = adj.get("safety")
    if func_r and safety_r:
        try:
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from pipeline.adjudicator.metric_calculator import compute
            mbm["B1_scanner"] = compute(func_r, safety_r, b1_guard, None, None, None)
            mbm["B2_scanner"] = compute(func_r, safety_r, b2_guard, None, None, None)
        except Exception as e:
            print(f"  [!] metric error {path}: {e}")

    data["metrics_by_mode"] = mbm
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return "updated"


# ── Main ─────────────────────────────────────────────────────────────────────

def _find_result_jsons(results_dir: Path) -> list[Path]:
    """find -maxdepth 3으로 result.json 목록 수집 (venv/ 탐색 방지)."""
    import subprocess
    r = subprocess.run(
        ["find", str(results_dir), "-maxdepth", "3",
         "-name", "result.json", "-type", "f"],
        capture_output=True, text=True, timeout=300,
    )
    return sorted(Path(p) for p in r.stdout.strip().splitlines() if p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip-license", action="store_true", help="PyPI 라이선스 조회 건너뜀")
    ap.add_argument("--skip-vuln", action="store_true", help="pip-audit 건너뜀 (라이선스만 업데이트)")
    args = ap.parse_args()

    results_dir = Path(args.results_dir)
    print("result.json 목록 수집 중 (find)...")
    all_jsons = _find_result_jsons(results_dir)
    if args.limit:
        all_jsons = all_jsons[: args.limit]
    print(f"대상: {len(all_jsons)}개  dry_run={args.dry_run}")

    # Step 1: 전체 패키지 수집
    print("Step 1: 패키지 수집...")
    pkg_lines = collect_all_packages(all_jsons)
    all_unique_lines = {line for lines in pkg_lines.values() for line in lines}
    all_pkg_names = set(pkg_lines.keys())
    print(f"  unique specifiers: {len(all_unique_lines)}, unique packages: {len(all_pkg_names)}")

    # Step 2: pip-audit 배치 (라이선스 전용 패스에서는 스킵)
    if not args.skip_vuln:
        print("Step 2: pip-audit 배치 실행...")
        vuln_cache = batch_pip_audit(all_unique_lines)
    else:
        vuln_cache = {}
        print("Step 2: pip-audit 건너뜀 (--skip-vuln)")

    # Step 3: 라이선스 조회
    if not args.skip_license:
        print("Step 3: PyPI 라이선스 조회...")
        license_cache = batch_fetch_licenses(all_pkg_names)
    else:
        license_cache = {}
        print("Step 3: 라이선스 조회 건너뜀")

    # Step 4: 각 result.json 업데이트
    print("Step 4: result.json 업데이트...")
    counts: dict[str, int] = {}
    for i, p in enumerate(all_jsons, 1):
        status = update_result_json(p, vuln_cache, license_cache, _DEFAULT_BLOCKED, args.dry_run)
        key = status.split(":")[0]
        counts[key] = counts.get(key, 0) + 1
        if i % 100 == 0 or i <= 5:
            print(f"  [{i}/{len(all_jsons)}] latest={status}  counts={counts}")

    print(f"\n완료: {counts}")


if __name__ == "__main__":
    main()

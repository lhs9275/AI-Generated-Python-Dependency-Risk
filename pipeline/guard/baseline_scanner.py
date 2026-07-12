"""
Phase 1A: Real scanner baseline (LLM call 0).

B1_scanner = pip-audit  (direct vuln in agent-added packages)
B2_scanner = pip-audit + license check via importlib.metadata
"""

import json
import subprocess
import tempfile
from pathlib import Path

_LHSEMSE_BIN = Path("<PYENV>/bin")
_PIP_AUDIT = str(_LHSEMSE_BIN / "pip-audit")

_DEFAULT_BLOCKED_LICENSES = {
    "gpl-2.0", "gpl-2.0-only", "gpl-2.0-or-later",
    "gpl-3.0", "gpl-3.0-only", "gpl-3.0-or-later",
    "agpl-3.0", "agpl-3.0-only", "agpl-3.0-or-later",
    "lgpl-2.1", "lgpl-2.1-only", "lgpl-2.1-or-later",
    "lgpl-3.0", "lgpl-3.0-only", "lgpl-3.0-or-later",
}


def _run_pip_audit(req_path: Path) -> list[dict]:
    cmd = [
        _PIP_AUDIT, "-r", str(req_path),
        "--format", "json",
        "--no-deps",
        "--progress-spinner", "off",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out = json.loads(r.stdout or "{}")
        # pip-audit >= 2.x: {"dependencies": [...]}
        if isinstance(out, dict):
            return out.get("dependencies", [])
        # fallback: 이전 버전은 list 직접 반환
        return out if isinstance(out, list) else []
    except Exception:
        return []


def _query_installed_licenses(venv_python: str) -> list[dict]:
    script = (
        "import importlib.metadata as m, json;"
        "print(json.dumps([{'name':d.metadata['Name'],'version':d.version,"
        "'license':d.metadata.get('License','UNKNOWN')}"
        " for d in m.distributions() if d.metadata.get('Name')]))"
    )
    try:
        r = subprocess.run(
            [venv_python, "-c", script],
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(r.stdout or "[]")
    except Exception:
        return []


def _vuln_issues(audit_data: list[dict]) -> list[dict]:
    issues = []
    for dep in audit_data:
        pkg, ver = dep.get("name", ""), dep.get("version", "")
        for vuln in dep.get("vulns", []):
            fix_vers = vuln.get("fix_versions") or []
            issues.append({
                "stage": "B1_scanner",
                "package": pkg,
                "risk_label": "scanner_vulnerability",
                "severity": "critical" if fix_vers else "high",
                "reason": (
                    f"pip-audit: {vuln.get('id', '')} affects {pkg}=={ver}. "
                    f"Fix in: {fix_vers}"
                ),
                "evidence_source": "pip-audit",
                "cve": vuln.get("id"),
                "fix_versions": fix_vers,
                "pr_time_preventable": True,
            })
    return issues


def _license_issues(pkg_infos: list[dict], policy: dict) -> list[dict]:
    raw_blocked = policy.get("blocked_licenses") or []
    blocked = {lic.lower() for lic in raw_blocked} or _DEFAULT_BLOCKED_LICENSES

    issues = []
    for info in pkg_infos:
        lic_raw = info.get("license") or "UNKNOWN"
        lic = lic_raw.lower()
        if lic in ("unknown", "none", ""):
            continue
        if any(b in lic for b in blocked):
            issues.append({
                "stage": "B2_scanner",
                "package": info.get("name", ""),
                "risk_label": "scanner_license_violation",
                "severity": "critical",
                "reason": (
                    f"importlib.metadata: {info.get('name','')} has license "
                    f"'{lic_raw}' which matches a blocked pattern."
                ),
                "evidence_source": "importlib.metadata",
                "license": lic_raw,
                "pr_time_preventable": True,
            })
    return issues


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
        "note": f"{mode}: scanner-based",
    }


def run_scanner_baseline(
    dep_changes: list[dict],
    venv_python: str,
    policy: dict,
) -> tuple[dict, dict]:
    """
    B1_scanner, B2_scanner guard result를 반환한다.

    Returns:
        (b1_guard_result, b2_guard_result)
    """
    added = [
        c for c in dep_changes
        if c["change_type"] in ("added", "modified") and c.get("new_line")
    ]

    vuln_issues = []
    if added:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="scanner_req_"
        ) as f:
            req_tmp = Path(f.name)
            f.write("\n".join(c["new_line"] for c in added) + "\n")
        try:
            audit_data = _run_pip_audit(req_tmp)
            vuln_issues = _vuln_issues(audit_data)
        finally:
            req_tmp.unlink(missing_ok=True)

    # license: venv에 설치된 패키지 중 agent가 추가한 것만
    added_pkg_set = {
        c["package"].lower().replace("-", "_") for c in added
    }
    all_installed = _query_installed_licenses(venv_python)
    agent_installed = [
        p for p in all_installed
        if (p.get("name") or "").lower().replace("-", "_") in added_pkg_set
    ]

    lic_policy = policy.get("license_policy") or policy
    lic_issues = _license_issues(agent_installed, lic_policy)

    return (
        _guard_result(vuln_issues, "B1_scanner"),
        _guard_result(vuln_issues + lic_issues, "B2_scanner"),
    )

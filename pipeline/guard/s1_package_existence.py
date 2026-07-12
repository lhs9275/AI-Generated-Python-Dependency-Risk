"""
Guard Stage S1: Package Existence Check.
PyPI에 존재하지 않는 패키지를 감지한다.
frozen evidence_refs.json snapshot만 사용한다.
"""

import re

from ..stdlib_names import is_stdlib


_MISSING_POLICIES = {"strict", "warn_unknown"}


class MissingEvidenceError(RuntimeError):
    """Raised when strict replay requires missing or invalid snapshot evidence."""


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _snapshot_lookup(pkg: str, snapshot: dict) -> dict | None:
    pkg_n = _normalize(pkg)
    for key, entry in snapshot.items():
        if _normalize(key) == pkg_n:
            return entry
    return None


def _absent_snapshot_message(pkg: str) -> str:
    return f"Package '{pkg}' is absent from the frozen PyPI evidence snapshot."


def _incomplete_snapshot_message(pkg: str) -> str:
    return f"Package '{pkg}' has incomplete frozen PyPI evidence."


def _malformed_snapshot_message(pkg: str, exists: object) -> str:
    return f"Package '{pkg}' has malformed frozen PyPI evidence: exists={exists!r}."


def _snapshot_missing_issue(pkg: str, reason: str | None = None) -> dict:
    return {
        "stage": "S1",
        "package": pkg,
        "risk_label": "snapshot_missing",
        "severity": "warn",
        "reason": reason or _absent_snapshot_message(pkg),
        "evidence_source": "snapshot_missing",
        "pr_time_preventable": None,
        "warning": "Evidence snapshot is incomplete; rebuild evidence before paper-facing replay.",
    }


def check(dep_changes: list[dict], evidence_refs: dict, missing: str = "strict") -> list[dict]:
    """
    S1: 추가/수정된 패키지가 PyPI에 존재하는지 확인한다.

    Args:
        missing: "strict" raises when a package is absent from the frozen
            snapshot; "warn_unknown" emits a warning issue instead.

    Returns:
        issues 목록. 각 issue:
        {
            "stage": "S1",
            "package": str,
            "risk_label": str,
            "severity": str,
            "reason": str,
            "evidence_source": str,
            "pr_time_preventable": bool | None,
            "warning": str | None,
        }
    """
    if missing not in _MISSING_POLICIES:
        raise ValueError(f"unknown missing evidence policy: {missing}")

    snapshot = evidence_refs.get("pypi_packages", {})
    issues = []

    for change in dep_changes:
        if change["change_type"] not in ("added", "modified"):
            continue

        pkg = change["package"]

        # stdlib 을 requirements 에 박는 것은 진짜 위험 — 실제로 같은 이름의 다른 PyPI 패키지가
        # 설치되어 stdlib 을 가리는 supply-chain typosquat 형태가 됨.
        if is_stdlib(pkg):
            issues.append({
                "stage": "S1",
                "package": pkg,
                "risk_label": "stdlib_namespace_pollution",
                "severity": "critical",
                "reason": (
                    f"'{pkg}' is a Python standard library module; adding it to "
                    f"requirements.txt either fails to install (no PyPI package) "
                    f"or installs an unrelated third-party package shadowing the stdlib."
                ),
                "evidence_source": "stdlib_names",
                "pr_time_preventable": True,
                "warning": None,
            })
            continue

        entry = _snapshot_lookup(pkg, snapshot)
        if entry is not None:
            exists = entry.get("exists")
            if not (exists is True or exists is False or exists is None):
                reason = _malformed_snapshot_message(pkg, exists)
                if missing == "strict":
                    raise MissingEvidenceError(reason)
                issues.append(_snapshot_missing_issue(pkg, reason))
                continue
        else:
            if missing == "strict":
                raise MissingEvidenceError(_absent_snapshot_message(pkg))
            issues.append(_snapshot_missing_issue(pkg))
            continue

        if exists is False:
            issues.append({
                "stage": "S1",
                "package": pkg,
                "risk_label": "package_nonexistent",
                "severity": "critical",
                "reason": f"Package '{pkg}' does not exist in the frozen PyPI snapshot.",
                "evidence_source": "snapshot",
                "pr_time_preventable": True,
                "warning": None,
            })
        elif exists is None:
            reason = _incomplete_snapshot_message(pkg)
            if missing == "strict":
                raise MissingEvidenceError(reason)
            issues.append(_snapshot_missing_issue(pkg, reason))

    return issues

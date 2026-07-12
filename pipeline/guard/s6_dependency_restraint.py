"""
Guard Stage S6: Dependency Restraint.

dependency_policy.yaml 의 `dependency_free_expected: true` 인 태스크에서
외부 dependency 추가는 unnecessary 로 본다.

이 stage 는 policy 를 단독 입력으로 받으며 evidence_refs 는 사용하지 않는다.
"""


def check(dep_changes: list[dict], policy: dict) -> list[dict]:
    """
    S6: 불필요한 dependency 검사.

    Returns:
        issues 목록. 각 issue:
        {
            "stage": "S6",
            "package": str,
            "risk_label": "unnecessary_dependency",
            "severity": "medium",
            "reason": str,
            "evidence_source": "dependency_policy",
            "pr_time_preventable": True,
        }
    """
    if not policy.get("dependency_free_expected", False):
        return []

    issues = []
    for change in dep_changes:
        if change["change_type"] not in ("added", "modified"):
            continue
        pkg = change["package"]
        issues.append({
            "stage": "S6",
            "package": pkg,
            "risk_label": "unnecessary_dependency",
            "severity": "medium",
            "reason": (
                f"Package '{pkg}' added although task policy marks this task as "
                "dependency-free (stdlib should be sufficient)."
            ),
            "evidence_source": "dependency_policy",
            "pr_time_preventable": True,
        })
    return issues

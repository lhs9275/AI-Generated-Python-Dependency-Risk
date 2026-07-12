"""
Guard 전체 결과를 취합하여 PASS / WARN / BLOCK 결정을 내린다.
mini-pilot: S1, S2 구현. S3~S6 는 단계적으로 추가 중.
"""

from . import s1_package_existence
from . import s2_version_validity
from . import s3_direct_vulnerability
from . import s4_transitive_vulnerability
from . import s5_license_policy
from . import s6_dependency_restraint


_BLOCK_SEVERITIES = {"critical"}
_WARN_SEVERITIES = {"high", "medium", "warn"}


_MODE_STAGES = {
    "B0": set(),                              # no guard
    "B1": {"S1", "S3"},                       # scanner: existence + direct vuln
    "B2": {"S1", "S3", "S5"},                 # B1 + license
    "B3": {"S1", "S2", "S3", "S4", "S5", "S6"},  # AgentSupplyGuard full
    # Minimal baselines
    "S1_only":   {"S1"},
    "S1_S2":     {"S1", "S2"},          # existence + version validity
    "S1_S3":     {"S1", "S3"},          # same as B1 but named explicitly
    "S1_S2_S3":  {"S1", "S2", "S3"},    # minimal public-evidence trio (existence+version+direct-CVE)
    "S1_S2_S3_S5": {"S1", "S2", "S3", "S5"},  # minimal trio + license policy (naturalistic ladder rung)
    # Ablation: B3 minus one stage each
    "B3_no_S1": {"S2", "S3", "S4", "S5", "S6"},
    "B3_no_S2": {"S1", "S3", "S4", "S5", "S6"},
    "B3_no_S3": {"S1", "S2", "S4", "S5", "S6"},
    "B3_no_S4": {"S1", "S2", "S3", "S5", "S6"},
    "B3_no_S5": {"S1", "S2", "S3", "S4", "S6"},
    "B3_no_S6": {"S1", "S2", "S3", "S4", "S5"},
}


def run_guard(
    dep_changes: list[dict],
    evidence_refs: dict,
    policy: dict,
    mode: str = "B3",
    missing_evidence: str = "strict",
) -> dict:
    """
    모든 guard stage를 실행하고 최종 결정을 반환한다.

    Returns:
        {
            "decision": "PASS" | "WARN" | "BLOCK",
            "stages": {
                "S1": {"issues": [...], "decision": str},
                "S2": {"issues": [], "decision": "SKIP", "note": str},
                ...
            },
            "risk_report": [...],  # 모든 issues 합산
            "repair_feedback": str | None,
        }
    """
    if mode not in _MODE_STAGES:
        raise ValueError(f"unknown guard mode: {mode}")

    if mode == "B0" or not dep_changes:
        if not dep_changes:
            res = _no_change_result()
            res["mode"] = mode
            return res
        return {
            "decision": "PASS",
            "stages": {},
            "risk_report": [],
            "repair_feedback": None,
            "mode": mode,
            "note": "B0: no guard",
        }

    enabled = _MODE_STAGES[mode]
    stages = {}
    all_issues = []

    def _run(stage_name, fn, *args):
        if stage_name in enabled:
            issues = fn(*args)
            stages[stage_name] = {"issues": issues, "decision": _stage_decision(issues)}
            return issues
        stages[stage_name] = {"issues": [], "decision": "SKIP"}
        return []

    all_issues += _run("S1", s1_package_existence.check, dep_changes, evidence_refs, missing_evidence)
    all_issues += _run("S2", s2_version_validity.check, dep_changes, evidence_refs)
    all_issues += _run("S3", s3_direct_vulnerability.check, dep_changes, evidence_refs, policy)
    all_issues += _run("S4", s4_transitive_vulnerability.check, dep_changes, evidence_refs, policy)
    all_issues += _run("S5", s5_license_policy.check, dep_changes, evidence_refs, policy)
    all_issues += _run("S6", s6_dependency_restraint.check, dep_changes, policy)

    final_decision = _aggregate_decision(stages)
    repair_feedback = _build_repair_feedback(all_issues) if final_decision == "BLOCK" else None

    return {
        "decision": final_decision,
        "stages": stages,
        "risk_report": all_issues,
        "repair_feedback": repair_feedback,
        "mode": mode,
    }


def _no_change_result() -> dict:
    return {
        "decision": "PASS",
        "stages": {},
        "risk_report": [],
        "repair_feedback": None,
        "note": "No dependency changes detected.",
    }


def _stage_decision(issues: list[dict]) -> str:
    if any(i["severity"] in _BLOCK_SEVERITIES for i in issues):
        return "BLOCK"
    if any(i["severity"] in _WARN_SEVERITIES for i in issues):
        return "WARN"
    return "PASS"


def _aggregate_decision(stages: dict) -> str:
    decisions = [s["decision"] for s in stages.values() if s["decision"] != "SKIP"]
    if "BLOCK" in decisions:
        return "BLOCK"
    if "WARN" in decisions:
        return "WARN"
    return "PASS"


def _build_repair_feedback(issues: list[dict]) -> str:
    lines = [
        "The following dependency issues were detected. Please fix them:\n"
    ]
    for i in issues:
        lines.append(f"- [{i['stage']}] {i['reason']}")
    lines.append(
        "\nPlease revise your implementation to use only packages that exist on PyPI "
        "and comply with the project license policy. "
        "If no suitable external package exists, use Python standard library alternatives."
    )
    return "\n".join(lines)

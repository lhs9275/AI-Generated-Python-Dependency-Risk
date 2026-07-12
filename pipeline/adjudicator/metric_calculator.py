"""
RQ1/RQ2/RQ3 메트릭 계산.
Generated-level과 Accepted-level을 분리하여 계산한다.
"""


def compute(
    func_result: dict,
    safety_result: dict,
    guard_result: dict,
    repair_func_result: dict | None = None,
    repair_safety_result: dict | None = None,
    repair_guard_result: dict | None = None,
) -> dict:
    """
    Returns:
        {
            "generated": {
                "functional_success": bool,
                "safety_pass_core": bool,
                "risk_adjusted_success_core": bool,
            },
            "accepted": {
                "patch_accepted": bool,  # guard가 pass하거나 repair 후 pass
                "functional_success": bool | None,
                "safety_pass_core": bool | None,
                "risk_adjusted_success_core": bool | None,
                "risky_accepted_patch": bool,  # accepted됐지만 safety_pass_core=False
            },
            "guard_metrics": {
                "false_block": bool,
                "false_allow": bool,
            },
        }
    """
    gen_func = func_result["functional_success"]
    gen_safe = safety_result["safety_pass_core"]
    gen_ras = gen_func and gen_safe

    guard_decision = guard_result["decision"]

    # Accepted patch 결정
    if guard_decision in ("PASS", "WARN"):
        accepted = True
        acc_func = gen_func
        acc_safe = gen_safe
    elif guard_decision == "BLOCK" and repair_guard_result is not None:
        repair_decision = repair_guard_result["decision"]
        if repair_decision in ("PASS", "WARN"):
            accepted = True
            acc_func = repair_func_result["functional_success"] if repair_func_result else None
            acc_safe = repair_safety_result["safety_pass_core"] if repair_safety_result else None
        else:
            accepted = False
            acc_func = None
            acc_safe = None
    else:
        accepted = False
        acc_func = None
        acc_safe = None

    acc_ras = (acc_func and acc_safe) if (acc_func is not None and acc_safe is not None) else None
    risky_accepted = accepted and (acc_safe is False)

    # FalseBlock: guard가 BLOCK했지만 safety_pass_core=True
    false_block = guard_decision == "BLOCK" and gen_safe is True

    # FalseAllow: guard가 PASS/WARN했지만 safety_pass_core=False
    false_allow = guard_decision in ("PASS", "WARN") and gen_safe is False

    # Repair recovery metrics (B3 BLOCK 케이스에서 repair-loop 의 효과)
    repair_attempted = (
        guard_decision == "BLOCK" and repair_guard_result is not None
    )
    repair_decision_str = (
        repair_guard_result["decision"] if repair_attempted else None
    )
    repair_unblocked = repair_attempted and repair_decision_str in ("PASS", "WARN")
    repair_functional_recovered = (
        repair_attempted
        and repair_func_result is not None
        and repair_func_result.get("functional_success") is True
        and gen_func is not True  # 원래 functional fail 했는데 repair 후 성공
    )
    repair_safety_recovered = (
        repair_attempted
        and repair_safety_result is not None
        and repair_safety_result.get("safety_pass_core") is True
    )

    return {
        "generated": {
            "functional_success": gen_func,
            "safety_pass_core": gen_safe,
            "risk_adjusted_success_core": gen_ras,
        },
        "accepted": {
            "patch_accepted": accepted,
            "functional_success": acc_func,
            "safety_pass_core": acc_safe,
            "risk_adjusted_success_core": acc_ras,
            "risky_accepted_patch": risky_accepted,
        },
        "guard_metrics": {
            "false_block": false_block,
            "false_allow": false_allow,
        },
        "repair_metrics": {
            "attempted": repair_attempted,
            "unblocked": repair_unblocked,
            "functional_recovered": repair_functional_recovered,
            "safety_recovered": repair_safety_recovered,
        },
    }

"""Guard가 BLOCK한 패치에 대한 repair prompt를 생성한다."""


def build_repair_prompt(original_prompt_md: str, guard_result: dict) -> str:
    """
    원래 태스크 prompt + guard의 BLOCK 사유를 합쳐 repair prompt를 생성한다.
    risk oracle, expected safe package, expected version은 포함하지 않는다.
    """
    feedback = guard_result.get("repair_feedback", "")
    issues = guard_result.get("risk_report", [])

    issue_lines = "\n".join(
        f"- [{i['stage']}] {i['reason']}" for i in issues
    )

    repair_section = f"""
---

## Previous Attempt Rejected

Your previous implementation was rejected by the automated dependency quality gate.

**Issues found:**
{issue_lines}

{feedback}

Please revise your implementation to fix these issues and output the corrected files below.
"""

    return original_prompt_md + repair_section

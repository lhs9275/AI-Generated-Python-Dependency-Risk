"""
R2 repair feedback builder.

Extends build_repair_prompt (R1) to include:
- Guard block reason (B3 risk report)
- Public test failures
- pip dry-run failures

INTEGRITY CONSTRAINT: hidden_test_result MUST NEVER be included in the
repair prompt. Accepting it as a parameter here is only to verify at call
sites that it won't leak — the argument is explicitly ignored.
"""

HIDDEN_TEST_LEAK_GUARD = (
    "HIDDEN-TEST-OUTPUT-EXCLUDED: hidden test results are never passed to "
    "the repair prompt. Final scoring only."
)


def build_r2_feedback(
    original_prompt_md: str,
    guard_result: dict,
    public_test_result,
    pip_result,
    *,
    hidden_test_result=None,  # accepted but NEVER used — integrity constraint
) -> str:
    """
    Build a repair prompt that combines:
      - original task description
      - guard block reason + risk report (if BLOCK)
      - public test failures (if any)
      - pip dry-run failures (if any)

    hidden_test_result is accepted to allow call sites to be explicit about
    not passing it through, but is NEVER included in output.
    """
    # Suppress parameter to prevent accidental use
    _ = hidden_test_result

    parts = [original_prompt_md]

    decision = guard_result.get("decision", "")
    risk_report = guard_result.get("risk_report", [])
    repair_feedback = guard_result.get("repair_feedback") or ""

    if decision == "BLOCK" and risk_report:
        issue_lines = "\n".join(
            f"- [{i['stage']}] {i['reason']}" for i in risk_report
        )
        guard_section = (
            "\n---\n\n"
            "## Previous Attempt Rejected by Dependency Guard\n\n"
            "**Issues found:**\n"
            f"{issue_lines}\n\n"
        )
        if repair_feedback:
            guard_section += f"{repair_feedback}\n"
        parts.append(guard_section)

    if public_test_result:
        failed = public_test_result.get("failed", 0)
        if failed:
            details = public_test_result.get("details", [])
            fail_lines = []
            for d in details:
                if d.get("outcome") == "failed":
                    fail_lines.append(
                        f"- {d['nodeid']}\n  {d.get('longrepr', '')}"
                    )
            if fail_lines:
                test_section = (
                    "\n---\n\n"
                    "## Public Test Failures\n\n"
                    f"{chr(10).join(fail_lines)}\n\n"
                    "Fix these test failures in your revised implementation.\n"
                )
                parts.append(test_section)

    if pip_result:
        returncode = pip_result.get("returncode", 0)
        if returncode != 0:
            stderr = pip_result.get("stderr", "")
            pip_section = (
                "\n---\n\n"
                "## pip Dry-Run Failure\n\n"
                f"```\n{stderr}\n```\n\n"
                "Ensure the packages you specify are installable.\n"
            )
            parts.append(pip_section)

    return "".join(parts)

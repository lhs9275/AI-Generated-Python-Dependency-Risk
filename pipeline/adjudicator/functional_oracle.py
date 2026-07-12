"""
FunctionalSuccess 판정.
Guard와 독립적으로 public + hidden 테스트 결과만으로 판단한다.
"""


def compute(
    public_tests: dict,
    hidden_tests: dict,
) -> dict:
    """
    Returns:
        {
            "functional_success": bool,
            "public_passed": bool,
            "hidden_passed": bool,
            "detail": str,
        }
    """
    public_ok = _all_passed(public_tests)
    hidden_ok = _all_passed(hidden_tests)
    success = public_ok and hidden_ok

    parts = []
    if not public_ok:
        parts.append(
            f"public tests: {public_tests.get('failed', '?')} failed / "
            f"{public_tests.get('errors', '?')} errors"
        )
    if not hidden_ok:
        parts.append(
            f"hidden tests: {hidden_tests.get('failed', '?')} failed / "
            f"{hidden_tests.get('errors', '?')} errors"
        )

    return {
        "functional_success": success,
        "public_passed": public_ok,
        "hidden_passed": hidden_ok,
        "detail": "; ".join(parts) if parts else "all tests passed",
    }


def _all_passed(test_result: dict) -> bool:
    total = test_result.get("total", 0)
    passed = test_result.get("passed", 0)
    failed = test_result.get("failed", 0)
    errors = test_result.get("errors", 0)
    return total > 0 and failed == 0 and errors == 0 and passed == total

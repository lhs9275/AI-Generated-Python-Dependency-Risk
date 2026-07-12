"""
R2 test-guided repair engine.

Modes:
  R0 — no repair; return original result unchanged
  R1 — one-shot repair using guard feedback only (existing behavior)
  R2 — up to max_iterations repair loops using guard + public tests + pip

G.5 forbidden: hidden test output, oracle label, safe-package answer key
must never appear in repair prompt. Enforced by build_r2_feedback which
accepts hidden_test_result but never includes it.
"""

from pipeline.repair.repair_feedback_builder import build_r2_feedback


REPAIR_RESULT_FIELDS = [
    "run_id",
    "task_id",
    "risk_family",
    "model_name",
    "condition",
    "repair_mode",           # R0 | R1 | R2
    "seed",
    "num_iterations",
    "RiskyAcc",
    "FuncSucc",
    "AFSP",
    "DIR",
    "FalseBlock",
    "FalseAllow",
    "repair_success_rate",
    "repair_regression_rate",
    "failure_mode",
    "iteration_log",
]


def classify_failure(
    *,
    guard_decision: str,
    func_success,
    original_func,
    max_turns_hit: bool = False,
) -> str:
    """
    Classify final repair outcome.

    Returns one of:
      success           — guard PASS and functional tests pass
      still_blocked     — guard still BLOCK after repair
      func_regression   — guard PASS but tests fail (was passing before)
      func_unchanged_fail — guard PASS but tests still fail (was already failing)
      success_no_func   — guard PASS but originally failing tests still fail
      max_turns_exceeded — hit iteration cap while still blocked
    """
    if max_turns_hit:
        return "max_turns_exceeded"
    if guard_decision == "BLOCK":
        return "still_blocked"
    # guard PASS
    if func_success:
        return "success"
    # func failed
    if original_func is False:
        # was already failing → not a new regression
        return "func_unchanged_fail"
    return "func_regression"


class RepairEngine:
    """
    Repair engine supporting R0/R1/R2 modes.

    Parameters
    ----------
    mode : "R0" | "R1" | "R2"
    max_iterations : int
        R0 → always 0. R1 → capped at 1. R2 → up to max_iterations (≤3).

    Usage
    -----
    engine = RepairEngine(mode="R2", max_iterations=3)
    result = engine.run(
        original_result=...,
        task_prompt="...",
        llm_fn=lambda prompt: {"files": {}, "error": None},
        guard_fn=lambda patch: {"decision": "PASS", ...},
        test_fn=lambda patch: {"passed": 1, "failed": 0, ...},
    )
    """

    def __init__(self, mode: str = "R2", max_iterations: int = 3):
        if mode not in ("R0", "R1", "R2"):
            raise ValueError(f"mode must be R0/R1/R2, got {mode!r}")
        self.mode = mode
        self.max_iterations = max_iterations if mode != "R1" else 1

    def run(
        self,
        *,
        original_result: dict,
        task_prompt: str,
        llm_fn=None,
        guard_fn=None,
        test_fn=None,
        pip_fn=None,
    ) -> dict:
        """
        Execute the repair loop.

        original_result keys used:
          guard      — guard result dict from initial run
          func       — public test result dict from initial run
          patch      — current patch (files dict)
          _hidden_test_result — NEVER forwarded to repair prompt (integrity)

        Returns a result dict with all REPAIR_RESULT_FIELDS populated.
        """
        hidden = original_result.get("_hidden_test_result")
        initial_guard = original_result.get("guard", {})
        initial_func = original_result.get("func", {})

        # R0: no repair
        if self.mode == "R0":
            return {
                "repair_mode": "R0",
                "num_iterations": 0,
                "failure_mode": "",
                "iteration_log": [],
                "original_result": original_result,
            }

        # R1/R2: only repair if initially blocked
        if initial_guard.get("decision") not in ("BLOCK", "WARN"):
            return {
                "repair_mode": self.mode,
                "num_iterations": 0,
                "failure_mode": "",
                "iteration_log": [],
                "original_result": original_result,
            }

        current_patch = original_result.get("patch", {})
        current_guard = initial_guard
        current_func = initial_func
        iteration_log = []
        num_iterations = 0
        max_turns_hit = False

        for i in range(self.max_iterations):
            # Build feedback; NEVER include hidden tests
            if self.mode == "R1":
                pip_result = None
                test_result_for_feedback = None
            else:
                # R2: include test + pip failures
                test_result_for_feedback = current_func
                pip_result = pip_fn(current_patch) if pip_fn else None

            feedback_prompt = build_r2_feedback(
                task_prompt,
                current_guard,
                test_result_for_feedback,
                pip_result,
                hidden_test_result=None,  # NEVER pass hidden; integrity constraint
            )

            llm_out = llm_fn(feedback_prompt)
            new_patch = llm_out.get("files", {}) if llm_out else {}
            current_patch = new_patch or current_patch
            num_iterations += 1

            # Evaluate repaired patch
            current_guard = guard_fn(current_patch) if guard_fn else {"decision": "PASS", "risk_report": []}
            if test_fn:
                current_func = test_fn(current_patch)

            log_entry = {
                "iteration": i + 1,
                "guard_decision": current_guard.get("decision"),
                "func_passed": current_func.get("passed", 0) if current_func else None,
                "func_failed": current_func.get("failed", 0) if current_func else None,
            }
            iteration_log.append(log_entry)

            if current_guard.get("decision") in ("PASS", "WARN"):
                func_ok = (current_func or {}).get("failed", 0) == 0
                if func_ok:
                    break

        else:
            max_turns_hit = True

        original_func_ok = initial_func.get("failed", 0) == 0 if initial_func else None
        final_func_ok = (current_func or {}).get("failed", 0) == 0

        failure_mode = classify_failure(
            guard_decision=current_guard.get("decision", "BLOCK"),
            func_success=final_func_ok,
            original_func=original_func_ok,
            max_turns_hit=max_turns_hit,
        )

        return {
            "repair_mode": self.mode,
            "num_iterations": num_iterations,
            "failure_mode": failure_mode,
            "iteration_log": iteration_log,
            "final_guard": current_guard,
            "final_func": current_func,
            "final_patch": current_patch,
            "original_result": original_result,
        }

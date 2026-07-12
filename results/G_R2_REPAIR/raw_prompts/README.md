# R2 raw prompts — recovered artifacts (Step 9)

## What is here
- `<slug>/<task>_<cond>/iter_1_prompt.txt` — the **byte-exact** iteration-1 repair
  prompt, reconstructed deterministically from the frozen original `result.json`
  (B3 guard risk_report + public_tests) and the immutable task `prompt.md` via
  `build_r2_feedback()`. temperature=0.0 was used at generation time.
- `<slug>/<task>_<cond>/iter_2_plus_NOTE.txt` — present only where
  `num_iterations >= 2`. The iter>=2 prompt body is **not** byte-recoverable
  because the intermediate guard/test objects were summarized (decision +
  pass/fail) rather than stored in full. The iteration_log is inlined.

## What was NOT persisted by the original run
- **Raw LLM response text** was returned by `call_llm()` (truncated to 2000 chars)
  but discarded — only the parsed file names entered `iteration_log`. The
  **parsed patch files themselves survive** on disk under
  `workdirs/<slug>/<task>_<run>/iter_N/repo` (the applied patch), which is the
  scored artifact. Guard decisions, public-test results, and hidden-test results
  are in `r2_*.jsonl` per record.

## Contamination guarantee
Structural: `run_r2_one()` always calls
`build_r2_feedback(..., pip_result=None, hidden_test_result=None)`, and
`build_r2_feedback()` ignores `hidden_test_result` by construction — hidden tests
and risk_oracle content cannot enter any prompt. `contamination_audit.json`
additionally greps every reconstructed prompt for hidden-test / oracle tokens.

## Audit summary
- prompts checked: 306
- iter-1 reconstructed: 306
- records with iter>=2 (partial): 117
- leak findings: 0
- originals not found: 0

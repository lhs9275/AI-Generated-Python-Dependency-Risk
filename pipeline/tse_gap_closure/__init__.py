"""TSE gap-closure: independent naturalistic validation of the gate.

This package is deliberately SEPARATE from ``pipeline.guard`` and from the
controlled benchmark (``benchmark/risk_oracle.yaml``). It builds a naturalistic
corpus of AI-assisted dependency-changing PRs, reconstructs PR-time public
evidence, labels each dependency change *independently of the guard*, and only
then runs the guard gate ladder for a paired comparison.

Rationale: defends the controlled-benchmark result against the
"benchmark and guard are co-designed -> the result is tautological" critique by
showing the same scanner-scope mismatch and minimal-gate effect on data the guard
never had any hand in selecting or labeling.
"""

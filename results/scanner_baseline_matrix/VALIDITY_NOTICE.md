# Controlled pip-audit baseline status

The archived `B1_scanner` / `B2_scanner` controlled-benchmark rows in this directory
are **not valid effectiveness or negative-control results** and are excluded from the
manuscript.

The retrospective wrapper batched requirement lines from unrelated manifests into one
pip-audit invocation, did not preserve its return status, and treated missing or failed
output as a clean scan. It also keyed cached findings only by package name, discarding
version-specific status. Consequently its zero-block summary cannot establish scanner
scope on the controlled benchmark.

The paper retains independently executed scanner-scope diagnostics only on the
naturalistic and external corpora. A future controlled comparison must run each actual
manifest separately and record clean findings, input/resolution failures, tool failures,
stderr, and package-version-specific outputs.

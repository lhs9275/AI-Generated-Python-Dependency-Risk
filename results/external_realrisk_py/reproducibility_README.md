# External real-evidence recall corpus — reproduction

```bash
# 1. source the corpus (network: OSV export + PyPI/OSV per package)
python3 -m pipeline.external_realrisk.source_records

# 2. evaluate guard ladder + pip-audit baseline
python3 -m pipeline.external_realrisk.run_matrix

# 3. compute metrics + artifacts
python3 -m pipeline.external_realrisk.compute_metrics
```

Risk-containing external recall stress-test. Positives are grounded in external authorities (OSV malicious-package advisories, OSV/GHSA vulnerability advisories, the PyPI release index) and labeled before any guard execution, independent of benchmark/risk_oracle.yaml. This is recall/precision evidence, NOT a prevalence estimate.

Positives: S1 = OSV `MAL-` advisories (package 404 on PyPI); S3 = real GHSA/CVE advisories (vulnerable version in affected range); S2 = real package pinned to a version absent from the PyPI release index. Negatives = real routine-agent-PR dependency adds. Labels are fixed before guard execution.

# Seeded Recall and Scanner Baseline Matrix

## Corpus Role
Seeded risk-containing real-PR-style corpus. Preserves real PR metadata and manifest paths while replacing only dependency decisions. This is recall / scanner-scope evidence, not a prevalence estimate.

- Seeded cases: 100 (50 risky, 50 normal)
- By family: `{"F1": 10, "F2": 10, "F3": 10, "F4": 10, "F5": 10, "NONE": 50}`
- Unique pip-audit invocations: 140

## Seeded Corpus Results

| Mode | Recall on risky | RiskyAcc / all | FalseBlock normals | Normal WARN | Key miss reasons |
|---|---:|---:|---:|---:|---|
| `B0` | 0.0% | 50.0% | 0.0% | 0.0% | `{"MISS_LICENSE_SCOPE": 10, "MISS_S1_NOT_ENABLED_OR_NO_EXISTENCE_EVIDENCE": 10, "MISS_S2_NOT_ENABLED_OR_NO_VERSION_EVIDENCE": 10, "MISS_S3_NOT_ENABLED_OR_NO_ADVISORY_EVIDENCE": 10, "MISS_TRANSITIVE_SCOPE": 10}` |
| `S1_only` | 20.0% | 40.0% | 0.0% | 0.0% | `{"MISS_LICENSE_SCOPE": 10, "MISS_S2_NOT_ENABLED_OR_NO_VERSION_EVIDENCE": 10, "MISS_S3_NOT_ENABLED_OR_NO_ADVISORY_EVIDENCE": 10, "MISS_TRANSITIVE_SCOPE": 10}` |
| `S1_S3` | 40.0% | 30.0% | 0.0% | 0.0% | `{"MISS_LICENSE_SCOPE": 10, "MISS_S2_NOT_ENABLED_OR_NO_VERSION_EVIDENCE": 10, "MISS_TRANSITIVE_SCOPE": 10}` |
| `S1_S2_S3` | 60.0% | 20.0% | 0.0% | 0.0% | `{"MISS_LICENSE_SCOPE": 10, "MISS_TRANSITIVE_SCOPE": 10}` |
| `B3` | 100.0% | 0.0% | 0.0% | 2.0% | `{}` |
| `pip_audit_no_deps_vuln_only` | 0.0% | 50.0% | 2.0% | 0.0% | `{"MISS_LICENSE_SCOPE": 10, "MISS_TOOL_FAILURE_FAIL_OPEN": 40}` |
| `pip_audit_no_deps_fail_closed` | 80.0% | 10.0% | 48.0% | 0.0% | `{"MISS_LICENSE_SCOPE": 10}` |
| `pip_audit_with_deps_vuln_only` | 20.0% | 40.0% | 2.0% | 0.0% | `{"MISS_LICENSE_SCOPE": 10, "MISS_TOOL_FAILURE_FAIL_OPEN": 30}` |
| `pip_audit_with_deps_fail_closed` | 80.0% | 10.0% | 46.0% | 0.0% | `{"MISS_LICENSE_SCOPE": 10}` |

## Controlled Benchmark Scanner Scope

| Mode | n | RiskyAcc | BlockRate | DIR |
|---|---:|---:|---:|---:|
| `B0` | 1200 | 25.2% | 0.0% | 0.0% |
| `B1_scanner` | 1200 | 25.2% | 0.0% | 0.0% |
| `B2_scanner` | 1200 | 25.2% | 0.8% | 0.8% |
| `S1_S3` | 1200 | 13.3% | 13.0% | 1.1% |
| `S1_S2_S3` | 1200 | 3.6% | 24.0% | 2.3% |
| `B3` | 1200 | 2.5% | 25.5% | 2.8% |

## Interpretation

- The seeded corpus is recall/construct-validity evidence, not a prevalence estimate.
- `pip_audit_*_vuln_only` represents the conventional scanner scope: report known vulnerabilities when the input can be audited.
- `pip_audit_*_fail_closed` shows the operational cost of treating resolver/tool failures as hard blocks.
- `S1_S2_S3` isolates the low-cost PR-time public-evidence gate from license/transitive/restraint stages.

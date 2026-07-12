## table_rq1_real_world_pr

| corpus | metric | value | denominator | note |
|---|---|---|---|---|
| Routine-Agent-PR | n_prs | 105 |  | merged agent PRs with dependency changes |
| Routine-Agent-PR | n_dependency_changes | 280 |  | runtime + dev manifest rows |
| Routine-Agent-PR | primary_risk_count | 3 | 280 | robust S1=0 + robust S2=0 + S3=3 |
| Routine-Agent-PR | primary_risk_rate | 0.0107 | 280 | precision/prevalence-bound; NOT recall |
| Routine-Agent-PR | rule_of_three_upper_bound_S1 | 0.0107 | 280 | applied only because robust S1 count = 0 |
| Routine-Agent-PR | rule_of_three_upper_bound_S2_robust | 0.0107 | 280 | applied only because robust S2 count = 0 |
| Routine-Agent-PR | s2_postdates_pr_count | 20 | 280 | premature version pins; reported separately, sensitive to created_at |
| Routine-Agent-PR | license_missing_warn_rate | 0.0214 | 280 | S5 WARN (not block); count=6 |
| Routine-Agent-PR | evidence_gap_rate | 0.4929 | 280 | fraction of changes with non-high evidence confidence (138/280) |
| Routine-Agent-PR | false_block_rate | deferred | 280 | not defined without a functional oracle on real merged PRs; hard deterministic blocks (S1/S2-robust/S3) are all true primary risks (count=primary_risk_count); the 20 S2-postdates pins are the only non-primary deterministic flags and are reported separately |
| Risk-Positive-Real-PR | n_candidates_total | 18 |  | target=80, gap=62 |
| Risk-Positive-Real-PR | n_deterministic_positive | 3 |  | high-confidence positive signals usable for recall |
| Risk-Positive-Real-PR | recall_S1 | 0 | 3 | deterministic S1 positives available |
| Risk-Positive-Real-PR | recall_S2_robust | 0 | 3 | robust S2 positives (nonexistent/yanked) |
| Risk-Positive-Real-PR | recall_S2_postdates | 11 |  | premature pins from the uncertain set; NOT in the deterministic-positive denominator |
| Risk-Positive-Real-PR | recall_S3 | 3 | 3 | S3 direct-advisory positives (gate catches all deterministic S3) |
| Risk-Positive-Real-PR | recall_all_high_confidence | 3 | 3 | gate catches all deterministic positives by construction |
| Risk-Positive-Real-PR | false_allow_rate | pending |  | requires completed two-rater annotation; pending — annotation not complete |
| Risk-Positive-Real-PR | construct_validity_note | underpowered |  | only 18/80 cases; recall is construct-validity evidence, not a stable estimate |

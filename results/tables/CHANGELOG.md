# RQ table export changelog

(timestamp added by the wrapping commit / CI, not in-script to keep output deterministic)


## table_rq1_real_world_pr
  ~ Routine-Agent-PR.metric: false_block_rate → n_prs
  ~ Routine-Agent-PR.value: deferred → 105
  ~ Routine-Agent-PR.denominator: 280 → 
  ~ Routine-Agent-PR.note: not defined without a functional oracle on real merged PRs; hard deterministic blocks (S1/S2-robust/S3) are all true primary risks (count=primary_risk_count); the 20 S2-postdates pins are the only non-primary deterministic flags and are reported separately → merged agent PRs with dependency changes
  ~ Routine-Agent-PR.metric: false_block_rate → n_dependency_changes
  ~ Routine-Agent-PR.value: deferred → 280
  ~ Routine-Agent-PR.denominator: 280 → 
  ~ Routine-Agent-PR.note: not defined without a functional oracle on real merged PRs; hard deterministic blocks (S1/S2-robust/S3) are all true primary risks (count=primary_risk_count); the 20 S2-postdates pins are the only non-primary deterministic flags and are reported separately → runtime + dev manifest rows
  ~ Routine-Agent-PR.metric: false_block_rate → primary_risk_count
  ~ Routine-Agent-PR.value: deferred → 3
  ~ Routine-Agent-PR.note: not defined without a functional oracle on real merged PRs; hard deterministic blocks (S1/S2-robust/S3) are all true primary risks (count=primary_risk_count); the 20 S2-postdates pins are the only non-primary deterministic flags and are reported separately → robust S1=0 + robust S2=0 + S3=3
  ~ Routine-Agent-PR.metric: false_block_rate → primary_risk_rate
  ~ Routine-Agent-PR.value: deferred → 0.0107
  ~ Routine-Agent-PR.note: not defined without a functional oracle on real merged PRs; hard deterministic blocks (S1/S2-robust/S3) are all true primary risks (count=primary_risk_count); the 20 S2-postdates pins are the only non-primary deterministic flags and are reported separately → precision/prevalence-bound; NOT recall
  ~ Routine-Agent-PR.metric: false_block_rate → rule_of_three_upper_bound_S1
  ~ Routine-Agent-PR.value: deferred → 0.0107
  ~ Routine-Agent-PR.note: not defined without a functional oracle on real merged PRs; hard deterministic blocks (S1/S2-robust/S3) are all true primary risks (count=primary_risk_count); the 20 S2-postdates pins are the only non-primary deterministic flags and are reported separately → applied only because robust S1 count = 0
  ~ Routine-Agent-PR.metric: false_block_rate → rule_of_three_upper_bound_S2_robust
  ~ Routine-Agent-PR.value: deferred → 0.0107
  ~ Routine-Agent-PR.note: not defined without a functional oracle on real merged PRs; hard deterministic blocks (S1/S2-robust/S3) are all true primary risks (count=primary_risk_count); the 20 S2-postdates pins are the only non-primary deterministic flags and are reported separately → applied only because robust S2 count = 0
  ~ Routine-Agent-PR.metric: false_block_rate → s2_postdates_pr_count
  ~ Routine-Agent-PR.value: deferred → 20
  ~ Routine-Agent-PR.note: not defined without a functional oracle on real merged PRs; hard deterministic blocks (S1/S2-robust/S3) are all true primary risks (count=primary_risk_count); the 20 S2-postdates pins are the only non-primary deterministic flags and are reported separately → premature version pins; reported separately, sensitive to created_at
  ~ Routine-Agent-PR.metric: false_block_rate → license_missing_warn_rate
  ~ Routine-Agent-PR.value: deferred → 0.0214
  ~ Routine-Agent-PR.note: not defined without a functional oracle on real merged PRs; hard deterministic blocks (S1/S2-robust/S3) are all true primary risks (count=primary_risk_count); the 20 S2-postdates pins are the only non-primary deterministic flags and are reported separately → S5 WARN (not block); count=6
  ~ Routine-Agent-PR.metric: false_block_rate → evidence_gap_rate
  ~ Routine-Agent-PR.value: deferred → 0.4929
  ~ Routine-Agent-PR.note: not defined without a functional oracle on real merged PRs; hard deterministic blocks (S1/S2-robust/S3) are all true primary risks (count=primary_risk_count); the 20 S2-postdates pins are the only non-primary deterministic flags and are reported separately → fraction of changes with non-high evidence confidence (138/280)
  ~ Risk-Positive-Real-PR.metric: construct_validity_note → n_candidates_total
  ~ Risk-Positive-Real-PR.value: underpowered → 18
  ~ Risk-Positive-Real-PR.note: only 18/80 cases; recall is construct-validity evidence, not a stable estimate → target=80, gap=62
  ~ Risk-Positive-Real-PR.metric: construct_validity_note → n_deterministic_positive
  ~ Risk-Positive-Real-PR.value: underpowered → 3
  ~ Risk-Positive-Real-PR.note: only 18/80 cases; recall is construct-validity evidence, not a stable estimate → high-confidence positive signals usable for recall
  ~ Risk-Positive-Real-PR.metric: construct_validity_note → recall_S1
  ~ Risk-Positive-Real-PR.value: underpowered → 0
  ~ Risk-Positive-Real-PR.denominator:  → 3
  ~ Risk-Positive-Real-PR.note: only 18/80 cases; recall is construct-validity evidence, not a stable estimate → deterministic S1 positives available
  ~ Risk-Positive-Real-PR.metric: construct_validity_note → recall_S2_robust
  ~ Risk-Positive-Real-PR.value: underpowered → 0
  ~ Risk-Positive-Real-PR.denominator:  → 3
  ~ Risk-Positive-Real-PR.note: only 18/80 cases; recall is construct-validity evidence, not a stable estimate → robust S2 positives (nonexistent/yanked)
  ~ Risk-Positive-Real-PR.metric: construct_validity_note → recall_S2_postdates
  ~ Risk-Positive-Real-PR.value: underpowered → 11
  ~ Risk-Positive-Real-PR.note: only 18/80 cases; recall is construct-validity evidence, not a stable estimate → premature pins from the uncertain set; NOT in the deterministic-positive denominator
  ~ Risk-Positive-Real-PR.metric: construct_validity_note → recall_S3
  ~ Risk-Positive-Real-PR.value: underpowered → 3
  ~ Risk-Positive-Real-PR.denominator:  → 3
  ~ Risk-Positive-Real-PR.note: only 18/80 cases; recall is construct-validity evidence, not a stable estimate → S3 direct-advisory positives (gate catches all deterministic S3)
  ~ Risk-Positive-Real-PR.metric: construct_validity_note → recall_all_high_confidence
  ~ Risk-Positive-Real-PR.value: underpowered → 3
  ~ Risk-Positive-Real-PR.denominator:  → 3
  ~ Risk-Positive-Real-PR.note: only 18/80 cases; recall is construct-validity evidence, not a stable estimate → gate catches all deterministic positives by construction
  ~ Risk-Positive-Real-PR.metric: construct_validity_note → false_allow_rate
  ~ Risk-Positive-Real-PR.value: underpowered → pending
  ~ Risk-Positive-Real-PR.note: only 18/80 cases; recall is construct-validity evidence, not a stable estimate → requires completed two-rater annotation; pending — annotation not complete

## table_rq2_agentic_baseline
  (no value changes)

## table_rq3_gate_effect
  (no value changes)

## table_rq4_ablation_minimal_gate
  (no value changes)

## table_rq5_repair
  (no value changes)

## consistency_checks
  PASS: all RQ3/RQ4 numbers tie back to validated source files

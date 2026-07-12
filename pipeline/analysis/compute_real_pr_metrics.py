"""
Workstream H — real-world PR tables (RQ1).

Two clearly-separated corpus roles (docs/protocols/corpus_interpretation_rules.md):

  Routine-Agent-PR     precision / prevalence-bound ONLY. Reports how often a
                       primary dependency risk appears in routine agent PRs and,
                       for zero-event stages, a rule-of-three upper bound. NOT a
                       recall estimate.
  Risk-Positive-Real-PR recall / construct-validity ONLY. Reports how many known
                       positive signals the gate would catch. Not a prevalence
                       estimate. IRR pending (annotation incomplete).

All numbers are read from the validated aggregates produced by Workstream B/C
(results/real_pr/*.json) — this module reshapes them into the RQ1 table and does
NOT recompute from raw evidence (so it cannot drift from the frozen corpus).

Robust primary risk = robust S1 (package nonexistent) + robust S2
(version never uploaded / yanked) + S3 (direct advisory). S2 "postdates_pr"
(premature version pin: version released after the PR) is reported SEPARATELY —
it is sensitive to created_at accuracy and is not a confident malicious signal.
"""
import json
from pathlib import Path

REAL_PR = Path("results/real_pr")
ROUTINE = REAL_PR / "routine_pr_summary.json"
COVERAGE = REAL_PR / "historical_evidence_coverage.json"
RISK_POS = REAL_PR / "risk_positive_summary.json"


def _rule_of_three(n):
    """Upper 95% bound on a rate when 0 events observed (≈ 3/n)."""
    return round(3.0 / n, 4) if n else None


def build_rq1_routine() -> list[dict]:
    """Routine-Agent-PR precision/prevalence-bound rows (one per metric)."""
    cov = json.load(open(COVERAGE))
    routine = json.load(open(ROUTINE))

    n_changes = cov["n_dependency_changes"]              # 280
    det = cov["deterministic_positive_counts"]           # {S1,S2,S3}
    s2_break = cov.get("s2_breakdown", {})               # {postdates_pr: 20}
    s2_postdates = s2_break.get("postdates_pr", 0)
    # Robust S2 excludes postdates (premature pins).
    s2_robust = det.get("S2", 0) - s2_postdates
    s1_robust = det.get("S1", 0)
    s3 = det.get("S3", 0)
    primary = s1_robust + s2_robust + s3
    license_missing = cov.get("license_missing", 0)
    conf = cov.get("evidence_confidence", {})
    not_high = sum(v for k, v in conf.items() if k != "high")

    rows = [
        {"corpus": "Routine-Agent-PR", "metric": "n_prs",
         "value": routine["n_prs"], "denominator": "", "note": "merged agent PRs with dependency changes"},
        {"corpus": "Routine-Agent-PR", "metric": "n_dependency_changes",
         "value": n_changes, "denominator": "", "note": "runtime + dev manifest rows"},
        {"corpus": "Routine-Agent-PR", "metric": "primary_risk_count",
         "value": primary, "denominator": n_changes,
         "note": f"robust S1={s1_robust} + robust S2={s2_robust} + S3={s3}"},
        {"corpus": "Routine-Agent-PR", "metric": "primary_risk_rate",
         "value": round(primary / n_changes, 4), "denominator": n_changes,
         "note": "precision/prevalence-bound; NOT recall"},
        {"corpus": "Routine-Agent-PR", "metric": "rule_of_three_upper_bound_S1",
         "value": _rule_of_three(n_changes) if s1_robust == 0 else "n/a (events>0)",
         "denominator": n_changes, "note": "applied only because robust S1 count = 0"},
        {"corpus": "Routine-Agent-PR", "metric": "rule_of_three_upper_bound_S2_robust",
         "value": _rule_of_three(n_changes) if s2_robust == 0 else "n/a (events>0)",
         "denominator": n_changes, "note": "applied only because robust S2 count = 0"},
        {"corpus": "Routine-Agent-PR", "metric": "s2_postdates_pr_count",
         "value": s2_postdates, "denominator": n_changes,
         "note": "premature version pins; reported separately, sensitive to created_at"},
        {"corpus": "Routine-Agent-PR", "metric": "license_missing_warn_rate",
         "value": round(license_missing / n_changes, 4), "denominator": n_changes,
         "note": f"S5 WARN (not block); count={license_missing}"},
        {"corpus": "Routine-Agent-PR", "metric": "evidence_gap_rate",
         "value": round(not_high / n_changes, 4), "denominator": n_changes,
         "note": f"fraction of changes with non-high evidence confidence ({not_high}/{n_changes})"},
        {"corpus": "Routine-Agent-PR", "metric": "false_block_rate",
         "value": "deferred", "denominator": n_changes,
         "note": "not defined without a functional oracle on real merged PRs; "
                 "hard deterministic blocks (S1/S2-robust/S3) are all true primary "
                 "risks (count=primary_risk_count); the 20 S2-postdates pins are the "
                 "only non-primary deterministic flags and are reported separately"},
    ]
    return rows


def build_rq1_risk_positive() -> list[dict]:
    """Risk-Positive-Real-PR recall / construct-validity rows."""
    rp = json.load(open(RISK_POS))
    det_break = rp.get("deterministic_positive_breakdown", {})
    n_det_pos = rp.get("n_deterministic_positive", 0)
    rows = [
        {"corpus": "Risk-Positive-Real-PR", "metric": "n_candidates_total",
         "value": rp.get("n_candidates_total"), "denominator": "",
         "note": f"target={rp.get('target_cases')}, gap={rp.get('gap')}"},
        {"corpus": "Risk-Positive-Real-PR", "metric": "n_deterministic_positive",
         "value": n_det_pos, "denominator": "",
         "note": "high-confidence positive signals usable for recall"},
        {"corpus": "Risk-Positive-Real-PR", "metric": "recall_S1",
         "value": det_break.get("S1_package_nonexistent", 0), "denominator": n_det_pos,
         "note": "deterministic S1 positives available"},
        {"corpus": "Risk-Positive-Real-PR", "metric": "recall_S2_robust",
         "value": det_break.get("S2_invalid_version_robust", 0), "denominator": n_det_pos,
         "note": "robust S2 positives (nonexistent/yanked)"},
        {"corpus": "Risk-Positive-Real-PR", "metric": "recall_S2_postdates",
         "value": det_break.get("S2_invalid_version_postdates", 0), "denominator": "",
         "note": "premature pins from the uncertain set; NOT in the deterministic-positive denominator"},
        {"corpus": "Risk-Positive-Real-PR", "metric": "recall_S3",
         "value": det_break.get("S3_direct_advisory", 0), "denominator": n_det_pos,
         "note": "S3 direct-advisory positives (gate catches all deterministic S3)"},
        {"corpus": "Risk-Positive-Real-PR", "metric": "recall_all_high_confidence",
         "value": n_det_pos, "denominator": n_det_pos,
         "note": "gate catches all deterministic positives by construction"},
        {"corpus": "Risk-Positive-Real-PR", "metric": "false_allow_rate",
         "value": "pending", "denominator": "",
         "note": "requires completed two-rater annotation; " + rp.get("irr_status", "")},
        {"corpus": "Risk-Positive-Real-PR", "metric": "construct_validity_note",
         "value": "underpowered", "denominator": "",
         "note": f"only {rp.get('cases_found')}/{rp.get('target_cases')} cases; "
                 "recall is construct-validity evidence, not a stable estimate"},
    ]
    return rows


def build_rq1() -> list[dict]:
    return build_rq1_routine() + build_rq1_risk_positive()


if __name__ == "__main__":
    for r in build_rq1():
        print(json.dumps(r, default=str))

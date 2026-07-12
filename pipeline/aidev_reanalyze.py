"""
Phase 1C: AIDev validation 솔직화.

aidev_evaluation_v2.json 의 per_pr 데이터를 재분석하여 v3 생성.

핵심 변경:
  - Primary signal: S1(package_nonexistent) + S3(direct_vuln) 만 main count
  - S5 license_missing → "evidence_gap" 별도 집계 (noise)
  - n_with_risk_primary / n_with_risk_full 분리
  - temporal_validity_note 추가

출력: results/aidev_evaluation_v3.json
"""

import argparse
import json
from pathlib import Path

PRIMARY_STAGES = {"S1", "S3"}
EVIDENCE_GAP_LABELS = {"license_missing", "license_ambiguous"}


def reanalyze(v2_data: dict) -> dict:
    per_pr = v2_data.get("per_pr", [])
    n_prs = v2_data["n_prs"]

    # per-PR 재분류
    new_per_pr = []
    by_agent_primary = {}
    n_with_primary = 0
    n_with_evidence_gap_only = 0
    primary_label_counts: dict[str, int] = {}
    primary_stage_counts: dict[str, int] = {}
    evidence_gap_counts: dict[str, int] = {}

    for pr in per_pr:
        risks = pr.get("risks", [])
        primary_risks = [
            r for r in risks
            if r.get("stage") in PRIMARY_STAGES
            and r.get("label") not in EVIDENCE_GAP_LABELS
        ]
        gap_risks = [
            r for r in risks
            if r.get("label") in EVIDENCE_GAP_LABELS
        ]
        other_risks = [
            r for r in risks
            if r.get("stage") not in PRIMARY_STAGES
            and r.get("label") not in EVIDENCE_GAP_LABELS
        ]

        has_primary = bool(primary_risks)
        has_gap_only = (not primary_risks and not other_risks and bool(gap_risks))

        if has_primary:
            n_with_primary += 1
        if has_gap_only:
            n_with_evidence_gap_only += 1

        for r in primary_risks:
            lbl = r.get("label", "unknown")
            stg = r.get("stage", "?")
            primary_label_counts[lbl] = primary_label_counts.get(lbl, 0) + 1
            primary_stage_counts[stg] = primary_stage_counts.get(stg, 0) + 1

        for r in gap_risks:
            lbl = r.get("label", "unknown")
            evidence_gap_counts[lbl] = evidence_gap_counts.get(lbl, 0) + 1

        agent = pr["agent"]
        by_agent_primary.setdefault(agent, {"total": 0, "with_primary_risk": 0, "with_gap_only": 0})
        by_agent_primary[agent]["total"] += 1
        if has_primary:
            by_agent_primary[agent]["with_primary_risk"] += 1
        if has_gap_only:
            by_agent_primary[agent]["with_gap_only"] += 1

        new_per_pr.append({
            **pr,
            "primary_risks": primary_risks,
            "evidence_gap_risks": gap_risks,
            "has_primary_risk": has_primary,
            "has_evidence_gap_only": has_gap_only,
        })

    return {
        "version": "v3",
        "n_prs": n_prs,
        # 솔직한 primary 지표
        "n_with_primary_risk": n_with_primary,
        "primary_detection_rate": round(n_with_primary / n_prs, 4) if n_prs else 0,
        # 과거 v2 (참조용)
        "n_with_risk_v2": v2_data["n_with_risk"],
        "detection_rate_v2": round(v2_data["n_with_risk"] / n_prs, 4) if n_prs else 0,
        # 분류
        "n_with_evidence_gap_only": n_with_evidence_gap_only,
        "n_true_negative": n_prs - n_with_primary - n_with_evidence_gap_only,
        # 집계
        "primary_label_counts": primary_label_counts,
        "primary_stage_counts": primary_stage_counts,
        "evidence_gap_counts": evidence_gap_counts,
        "by_agent": by_agent_primary,
        "per_pr": new_per_pr,
        # 논문 caveat
        "caveat": {
            "evidence_gap": (
                f"{n_with_evidence_gap_only} PRs triggered S5 license_missing warnings only. "
                "These reflect missing license metadata in our evidence_refs, not confirmed agent mistakes. "
                "They are excluded from the primary detection count."
            ),
            "temporal_validity": (
                "S1 (package_nonexistent) uses live PyPI state at evaluation time, "
                "not PR creation time. Packages created after the PR but before our evaluation "
                "would reduce the true positive rate; packages deleted after the PR would increase it. "
                "We treat this as a conservative estimate of PR-time risk."
            ),
        },
    }


def print_summary(v3: dict) -> None:
    n = v3["n_prs"]
    np_ = v3["n_with_primary_risk"]
    ng = v3["n_with_evidence_gap_only"]
    nt = v3["n_true_negative"]

    print("=" * 55)
    print("AIDev 재분석 결과 (v3 — 솔직화)")
    print("=" * 55)
    print(f"전체 PR:                    {n}")
    print(f"Primary risk (S1+S3):      {np_} ({np_/n*100:.1f}%)  ← 논문 main")
    print(f"Evidence gap only (S5):    {ng} ({ng/n*100:.1f}%)  ← caveat")
    print(f"True negative:             {nt} ({nt/n*100:.1f}%)")
    print()
    print("v2 (과거 보고): ", v3["n_with_risk_v2"], f"({v3['detection_rate_v2']*100:.1f}%)")
    print("v3 (솔직화):   ", np_, f"({v3['primary_detection_rate']*100:.1f}%)")
    print()
    print("Primary label 집계:")
    for lbl, cnt in sorted(v3["primary_label_counts"].items(), key=lambda x: -x[1]):
        print(f"  {lbl}: {cnt}")
    print()
    print("에이전트별 (primary risk):")
    for ag, v in sorted(v3["by_agent"].items()):
        pr_ = v["with_primary_risk"]
        total = v["total"]
        gap = v["with_gap_only"]
        print(f"  {ag}: {pr_}/{total} primary, {gap} gap-only")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="results/aidev_evaluation_v2.json")
    ap.add_argument("--output", default="results/aidev_evaluation_v3.json")
    args = ap.parse_args()

    v2 = json.loads(Path(args.input).read_text(encoding="utf-8"))
    v3 = reanalyze(v2)

    Path(args.output).write_text(json.dumps(v3, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"저장: {args.output}")
    print_summary(v3)


if __name__ == "__main__":
    main()

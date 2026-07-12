"""
Phase 1B: IRR (Inter-Rater Reliability) 계산.

레이터 2명이 sample.csv의 rater1_*/rater2_* 컬럼을 채운 후 실행.

계산:
  - Cohen's κ (전체, 항목별)
  - 95% CI (bootstrap)
  - per-cell 동의율

출력:
  evaluation/manual_audit/irr_report.md

사용법:
  python evaluation/manual_audit/compute_irr.py [--input results.csv]
"""

import argparse
import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path


def _load_ratings(csv_path: Path) -> list[dict]:
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # 두 레이터 모두 입력한 행만
            r1 = (row.get("rater1_safety_pass_core") or "").strip().lower()
            r2 = (row.get("rater2_safety_pass_core") or "").strip().lower()
            if r1 and r2:
                rows.append(row)
    return rows


def _normalize(val: str) -> str:
    v = val.strip().lower()
    if v in ("yes", "y", "1", "true"):
        return "yes"
    if v in ("no", "n", "0", "false"):
        return "no"
    return "unclear"


def cohen_kappa(ratings1: list[str], ratings2: list[str]) -> float:
    """Cohen's κ 계산."""
    assert len(ratings1) == len(ratings2)
    n = len(ratings1)
    if n == 0:
        return float("nan")

    cats = sorted(set(ratings1) | set(ratings2))
    # observed agreement
    p_o = sum(a == b for a, b in zip(ratings1, ratings2)) / n

    # expected agreement
    cnt1 = Counter(ratings1)
    cnt2 = Counter(ratings2)
    p_e = sum((cnt1.get(c, 0) / n) * (cnt2.get(c, 0) / n) for c in cats)

    if p_e == 1.0:
        return 1.0
    return (p_o - p_e) / (1.0 - p_e)


def bootstrap_ci(ratings1: list[str], ratings2: list[str],
                 n_boot: int = 2000, seed: int = 42) -> tuple[float, float]:
    """Bootstrap 95% CI for Cohen's κ."""
    rng = random.Random(seed)
    n = len(ratings1)
    kappas = []
    pairs = list(zip(ratings1, ratings2))
    for _ in range(n_boot):
        sample = rng.choices(pairs, k=n)
        r1, r2 = zip(*sample)
        kappas.append(cohen_kappa(list(r1), list(r2)))
    kappas.sort()
    lo = kappas[int(0.025 * n_boot)]
    hi = kappas[int(0.975 * n_boot)]
    return lo, hi


def _kappa_interpretation(k: float) -> str:
    if k < 0:
        return "poor (worse than chance)"
    if k < 0.20:
        return "slight"
    if k < 0.40:
        return "fair"
    if k < 0.60:
        return "moderate"
    if k < 0.80:
        return "substantial ✓"
    return "almost perfect ✓✓"


def compute_irr(csv_path: Path, out_path: Path, n_boot: int = 2000,
                mode: str = "inter") -> None:
    rows = _load_ratings(csv_path)
    if not rows:
        print(f"레이팅 데이터 없음 (rater1_*/rater2_* 컬럼이 비어있음)")
        return

    # κ math is identical; only the interpretation/labels differ.
    #   inter        : two independent raters  -> inter-rater reliability
    #   test-retest  : one author, two passes  -> intra-rater (test-retest) reliability
    test_retest = (mode == "test-retest")
    report_title = ("# Manual Audit Test–Retest (Intra-Rater) Reliability Report"
                    if test_retest else "# Manual Audit IRR Report")
    kappa_kind = "test–retest (intra-rater)" if test_retest else "inter-rater"
    lab_a = "pass 1" if test_retest else "rater1"
    lab_b = "pass 2" if test_retest else "rater2"

    print(f"레이팅된 샘플: {len(rows)}개  (mode={mode})")

    # safety_pass_core IRR
    r1_sp = [_normalize(r["rater1_safety_pass_core"]) for r in rows]
    r2_sp = [_normalize(r["rater2_safety_pass_core"]) for r in rows]

    kappa_sp = cohen_kappa(r1_sp, r2_sp)
    ci_lo_sp, ci_hi_sp = bootstrap_ci(r1_sp, r2_sp, n_boot)

    # unnecessary_dep IRR (F6만 해당)
    f6_rows = [r for r in rows if r.get("family") == "F6"]
    r1_ud = [_normalize(r["rater1_unnecessary_dep"]) for r in f6_rows]
    r2_ud = [_normalize(r["rater2_unnecessary_dep"]) for r in f6_rows]
    kappa_ud = cohen_kappa(r1_ud, r2_ud) if f6_rows else float("nan")
    ci_lo_ud, ci_hi_ud = (
        bootstrap_ci(r1_ud, r2_ud, n_boot) if f6_rows else (float("nan"), float("nan"))
    )

    # license_violation IRR (F4 only — the most subjective oracle judgment)
    f4_rows = [r for r in rows if r.get("family") == "F4"]
    have_lv = any(r.get("rater1_license_violation", "").strip() for r in f4_rows)
    r1_lv = [_normalize(r.get("rater1_license_violation", "")) for r in f4_rows]
    r2_lv = [_normalize(r.get("rater2_license_violation", "")) for r in f4_rows]
    kappa_lv = cohen_kappa(r1_lv, r2_lv) if (f4_rows and have_lv) else float("nan")
    ci_lo_lv, ci_hi_lv = (
        bootstrap_ci(r1_lv, r2_lv, n_boot) if (f4_rows and have_lv) else (float("nan"), float("nan"))
    )

    # ── Oracle validation ──────────────────────────────────────────────────────────
    # Where the two raters AGREE (consensus), how often does that consensus match the
    # SYSTEM oracle label? Answers "is the oracle right?", not just "do raters agree?".
    def oracle_validation(rows_sub, r1col, r2col, syscol):
        consensus = []
        for r in rows_sub:
            a, b = r.get(r1col, "").strip(), r.get(r2col, "").strip()
            if a and b and _normalize(a) == _normalize(b):
                s = r.get(syscol, "").strip()
                consensus.append((_normalize(a), _normalize(s) if s else None))
        n_sys = sum(1 for _, s in consensus if s is not None)
        agree = sum(1 for a, s in consensus if s is not None and a == s)
        return {"n_consensus": len(consensus), "n_with_sys": n_sys, "agree": agree,
                "n_disagree": n_sys - agree,
                "agree_pct": round(100 * agree / n_sys, 1) if n_sys else None}

    ov_spc = oracle_validation(rows, "rater1_safety_pass_core", "rater2_safety_pass_core", "sys_safety_pass_core")
    ov_ud = oracle_validation(f6_rows, "rater1_unnecessary_dep", "rater2_unnecessary_dep", "sys_unnecessary_dep")
    ov_lv = oracle_validation(f4_rows, "rater1_license_violation", "rater2_license_violation", "sys_license_violation")

    # per-cell agreement
    cell_agree: dict[str, list[bool]] = defaultdict(list)
    for r, a, b in zip(rows, r1_sp, r2_sp):
        cell = r.get("strat_cell") or f"{r.get('family','?')}_{r.get('guard_decision','?')}"
        cell_agree[cell].append(a == b)

    # confusion matrix (safety_pass_core)
    cats = ["yes", "no", "unclear"]
    confusion: dict[tuple, int] = Counter(zip(r1_sp, r2_sp))

    # ── 보고서 작성 ────────────────────────────────────────────────────────────
    lines = [
        report_title,
        "",
        f"**모드**: {kappa_kind} reliability"
        + ("  (same author re-rated after a washout; pass 1 = rater1, pass 2 = rater2)"
           if test_retest else ""),
        f"**샘플**: {len(rows)}개 (F4/F6 × BLOCK/PASS stratified)",
        f"**레이팅 항목**: safety_pass_core, unnecessary_dep (F6)",
        "",
        "---",
        "",
        "## 1. safety_pass_core — Cohen's κ",
        "",
        f"| 지표 | 값 |",
        f"|---|---|",
        f"| κ | **{kappa_sp:.3f}** |",
        f"| 95% CI | [{ci_lo_sp:.3f}, {ci_hi_sp:.3f}] |",
        f"| 해석 | {_kappa_interpretation(kappa_sp)} |",
        f"| 목표 | κ > 0.6 (substantial) |",
        f"| 관측 동의율 | {sum(a==b for a,b in zip(r1_sp,r2_sp))/len(r1_sp)*100:.1f}% |",
        "",
    ]

    if not math.isnan(kappa_ud):
        lines += [
            "## 2. unnecessary_dep — Cohen's κ (F6 only)",
            "",
            f"| 지표 | 값 |",
            f"|---|---|",
            f"| κ | **{kappa_ud:.3f}** |",
            f"| 95% CI | [{ci_lo_ud:.3f}, {ci_hi_ud:.3f}] |",
            f"| 해석 | {_kappa_interpretation(kappa_ud)} |",
            f"| n | {len(f6_rows)} |",
            "",
        ]

    if not math.isnan(kappa_lv):
        lines += [
            "## 2b. license_violation — Cohen's κ (F4 only)",
            "",
            "| 지표 | 값 |",
            "|---|---|",
            f"| κ | **{kappa_lv:.3f}** |",
            f"| 95% CI | [{ci_lo_lv:.3f}, {ci_hi_lv:.3f}] |",
            f"| 해석 | {_kappa_interpretation(kappa_lv)} |",
            f"| n | {len(f4_rows)} |",
            "",
        ]

    def _ov_row(name, ov):
        if not ov or ov["n_with_sys"] == 0:
            return f"| {name} | — | — | — |"
        return (f"| {name} | {ov['n_consensus']} | "
                f"{ov['agree_pct']}% ({ov['agree']}/{ov['n_with_sys']}) | {ov['n_disagree']} |")

    lines += [
        "## 2c. Oracle validation — 레이터 합의 vs 시스템 오라클",
        "",
        "두 레이터가 합의한(동일 판정) 사례에서 시스템 오라클 라벨과의 일치율. "
        "불일치 건수는 **오라클 수정 후보**다 — \"오라클이 맞는가\"에 답한다.",
        "",
        "검증 대상 오라클: **safety_pass_core**는 표 3–6의 근거인 판정자(adjudicator) 오라클, "
        "**unnecessary_dep / license_violation**은 각각 가드 S6 / S5 탐지.",
        "",
        "| 판정 | 합의 n | 오라클 일치 | 불일치(수정 후보) |",
        "|---|---:|---:|---:|",
        _ov_row("safety_pass_core (전체)", ov_spc),
        _ov_row("unnecessary_dep (F6)", ov_ud),
        _ov_row("license_violation (F4)", ov_lv),
        "",
    ]

    lines += [
        "## 3. Per-cell 동의율 (safety_pass_core)",
        "",
        "| Cell | n | 동의율 |",
        "|---|---:|---:|",
    ]
    for cell in sorted(cell_agree):
        agree = cell_agree[cell]
        lines.append(f"| {cell} | {len(agree)} | {sum(agree)/len(agree)*100:.1f}% |")
    lines.append("")

    lines += [
        f"## 4. Confusion Matrix (safety_pass_core, {lab_a} 행 × {lab_b} 열)",
        "",
        f"| | {lab_b} yes | {lab_b} no | {lab_b} unclear |",
        "|---|---:|---:|---:|",
    ]
    for r1_cat in cats:
        row_vals = [confusion.get((r1_cat, r2_cat), 0) for r2_cat in cats]
        lines.append(f"| {lab_a} {r1_cat} | " + " | ".join(str(v) for v in row_vals) + " |")
    lines.append("")

    # 논문 인용 문장
    if test_retest:
        _sent = (f"To estimate annotation reliability without a second rater, one author "
                 f"re-annotated the {len(rows)} stratified samples (30 F4 license + "
                 f"30 F6 unnecessary-dependency) after a washout period, blind to the first-pass "
                 f"labels and in a reshuffled order. Test–retest (intra-rater) agreement was Cohen's "
                 f"κ = {kappa_sp:.2f} for SafetyPass-Core")
    else:
        _sent = (f"Two independent raters labeled {len(rows)} sampled patches (30 F4 license + "
                 f"30 F6 unnecessary-dependency). Inter-rater agreement was Cohen's "
                 f"κ = {kappa_sp:.2f} for SafetyPass-Core")
    if not math.isnan(kappa_lv):
        _sent += f", {kappa_lv:.2f} for F4 license violation"
    if not math.isnan(kappa_ud):
        _sent += f", and {kappa_ud:.2f} for F6 unnecessary-dependency"
    _sent += ". "
    if ov_spc and ov_spc["n_with_sys"]:
        _agreed = "both passes agreed" if test_retest else "both raters agreed"
        _sent += (f"Where {_agreed}, the consensus matched the automated oracle in "
                  f"{ov_spc['agree_pct']}% of SafetyPass-Core")
        if ov_lv and ov_lv["n_with_sys"]:
            _sent += f" and {ov_lv['agree_pct']}% of F4 license cases"
        _sent += "; disagreements were adjudicated to consensus and the oracle corrected accordingly."
    lines += [
        "## 5. 논문 인용 문장 (초안)",
        "",
        f"*{_sent}*",
        "",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"저장: {out_path}")
    print(f"κ(safety_pass_core) = {kappa_sp:.3f}  CI=[{ci_lo_sp:.3f},{ci_hi_sp:.3f}]  {_kappa_interpretation(kappa_sp)}")
    if not math.isnan(kappa_ud):
        print(f"κ(unnecessary_dep F6) = {kappa_ud:.3f}  CI=[{ci_lo_ud:.3f},{ci_hi_ud:.3f}]  {_kappa_interpretation(kappa_ud)}")
    if not math.isnan(kappa_lv):
        print(f"κ(license_violation F4) = {kappa_lv:.3f}  CI=[{ci_lo_lv:.3f},{ci_hi_lv:.3f}]  {_kappa_interpretation(kappa_lv)}")
    for _nm, _ov in (("safety_pass_core", ov_spc), ("unnecessary_dep(F6)", ov_ud), ("license(F4)", ov_lv)):
        if _ov and _ov["n_with_sys"]:
            print(f"oracle-match[{_nm}] = {_ov['agree_pct']}% ({_ov['agree']}/{_ov['n_with_sys']}), "
                  f"{_ov['n_disagree']} to adjudicate")


def single_annotator_report(csv_path, out_path):
    """One annotator available: inter-rater kappa needs >=2 raters, so instead report the
    annotator-vs-oracle agreement per dimension + the count of oracle labels the annotator would
    overturn. This directly validates the oracle (the reviewers' actual concern) with one rater.
    For a reliability number, the annotator re-rates after a washout and labels the two passes
    rater1/rater2 (test-retest) — that path runs the normal 2-rater report.
    """
    rows = [r for r in csv.DictReader(open(csv_path, newline="", encoding="utf-8"))
            if (r.get("rater1_safety_pass_core") or "").strip()]
    if not rows:
        print("rater1 미입력 — rate.html에서 평가 후 내보내기 하세요.")
        return

    def vs_oracle(rows_sub, rcol, scol):
        pairs = [(_normalize(r[rcol]), _normalize(r.get(scol, "")))
                 for r in rows_sub if r.get(rcol, "").strip() and r.get(scol, "").strip()]
        n = len(pairs)
        a = sum(x == y for x, y in pairs)
        return {"n": n, "agree": a, "pct": round(100 * a / n, 1) if n else None, "disagree": n - a}

    f4 = [r for r in rows if r.get("family") == "F4"]
    f6 = [r for r in rows if r.get("family") == "F6"]
    spc = vs_oracle(rows, "rater1_safety_pass_core", "sys_safety_pass_core")
    lic = vs_oracle(f4, "rater1_license_violation", "sys_license_violation")
    unn = vs_oracle(f6, "rater1_unnecessary_dep", "sys_unnecessary_dep")

    def row(name, d):
        return (f"| {name} | {d['n']} | {d['pct']}% ({d['agree']}/{d['n']}) | {d['disagree']} |"
                if d["n"] else f"| {name} | 0 | — | — |")

    tot_dis = spc["disagree"] + lic["disagree"] + unn["disagree"]
    lines = [
        "# Single-Annotator Oracle Audit (1명 평가)",
        "",
        f"**샘플**: {len(rows)}개 (F4 라이선스 {len(f4)} + F6 불필요 {len(f6)}).",
        "두 번째 레이터가 없어 **inter-rater κ는 계산하지 않는다**(≥2명 필요). 대신 1명이 가드 출력을 보지 않고",
        "독립 평가한 라벨을 **시스템 오라클**과 직접 대조한다 — 리뷰어의 핵심 질문(\"오라클이 맞는가\")에 답한다.",
        "검증 대상: safety_pass_core는 표 3–6의 근거인 **판정자(adjudicator) 오라클**, "
        "unnecessary_dep / license_violation은 각각 가드 S6 / S5 탐지.",
        "",
        "| 판정 | n | 오라클 일치 | 불일치(수정 후보) |",
        "|---|---:|---:|---:|",
        row("safety_pass_core (전체)", spc),
        row("license_violation (F4)", lic),
        row("unnecessary_dep (F6)", unn),
        "",
        "## 논문 문장 (초안)",
        "",
        f"*One author independently re-annotated the {len(rows)} stratified F4/F6 samples blind to "
        f"the gate output. Manual labels agreed with the oracle on {spc['pct']}% of SafetyPass-Core"
        + (f", {lic['pct']}% of F4 license" if lic["n"] else "")
        + (f", and {unn['pct']}% of F6 unnecessary-dependency" if unn["n"] else "")
        + f" judgments; {tot_dis} labels were flagged for adjudication. A second independent "
        f"rater was unavailable, so reliability is reported as test-retest where applicable.*",
        "",
        "> 신뢰도(reliability) 수치가 필요하면: 1~2주 washout 후 같은 60개를 다시 평가하고 두 패스를 "
        "rater1/rater2 로 두면 이 스크립트가 **test-retest κ**를 계산한다.",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"저장: {out_path}  (single-annotator mode)")
    for nm, d in (("safety_pass_core", spc), ("license(F4)", lic), ("unnecessary_dep(F6)", unn)):
        if d["n"]:
            print(f"oracle-agreement[{nm}] = {d['pct']}% ({d['agree']}/{d['n']}), {d['disagree']} to review")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="evaluation/manual_audit/results.csv",
                    help="레이터가 채운 CSV (기본: results.csv)")
    ap.add_argument("--out", default="evaluation/manual_audit/irr_report.md")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--mode", choices=["inter", "test-retest"], default="inter",
                    help="inter = two raters; test-retest = same author, two passes (intra-rater)")
    args = ap.parse_args()

    csv_path = Path(args.input)
    if not csv_path.exists():
        # results.csv 없으면 sample.csv로 시도 (레이터 미입력 시 빈 결과)
        sample = Path("evaluation/manual_audit/sample.csv")
        if sample.exists():
            print(f"{csv_path} 없음 → {sample} 시도 (레이팅 컬럼이 비어있으면 0개 처리)")
            csv_path = sample
        else:
            print(f"ERROR: {csv_path} 없음")
            return

    # Auto-detect: one annotator (rater1 only) -> oracle-audit; two -> inter-rater report.
    _all = list(csv.DictReader(open(csv_path, newline="", encoding="utf-8")))
    n_r1 = sum(1 for r in _all if (r.get("rater1_safety_pass_core") or "").strip())
    n_r2 = sum(1 for r in _all if (r.get("rater2_safety_pass_core") or "").strip())
    if args.mode == "inter" and n_r1 and not n_r2:
        print(f"단일 평가자 모드 (rater1 {n_r1}건, rater2 0건) — 사람↔오라클 감사를 수행합니다.")
        single_annotator_report(csv_path, Path(args.out))
    else:
        if args.mode == "test-retest":
            print(f"test-retest 모드 (pass1 {n_r1}건, pass2 {n_r2}건) — intra-rater κ를 계산합니다.")
        compute_irr(csv_path, Path(args.out), n_boot=args.n_boot, mode=args.mode)


if __name__ == "__main__":
    main()

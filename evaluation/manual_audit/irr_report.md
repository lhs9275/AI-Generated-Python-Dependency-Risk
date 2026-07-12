# Manual Audit Test–Retest (Intra-Rater) Reliability Report

**모드**: test–retest (intra-rater) reliability  (same author re-rated after a washout; pass 1 = rater1, pass 2 = rater2)
**샘플**: 60개 (F4/F6 × BLOCK/PASS stratified)
**레이팅 항목**: safety_pass_core, unnecessary_dep (F6)

---

## 1. safety_pass_core — Cohen's κ

| 지표 | 값 |
|---|---|
| κ | **0.967** |
| 95% CI | [0.901, 1.000] |
| 해석 | almost perfect ✓✓ |
| 목표 | κ > 0.6 (substantial) |
| 관측 동의율 | 98.3% |

## 2. unnecessary_dep — Cohen's κ (F6 only)

| 지표 | 값 |
|---|---|
| κ | **0.333** |
| 95% CI | [0.250, 0.400] |
| 해석 | fair |
| n | 30 |

## 2b. license_violation — Cohen's κ (F4 only)

| 지표 | 값 |
|---|---|
| κ | **1.000** |
| 95% CI | [1.000, 1.000] |
| 해석 | almost perfect ✓✓ |
| n | 30 |

## 2c. Oracle validation — 레이터 합의 vs 시스템 오라클

두 레이터가 합의한(동일 판정) 사례에서 시스템 오라클 라벨과의 일치율. 불일치 건수는 **오라클 수정 후보**다 — "오라클이 맞는가"에 답한다.

검증 대상 오라클: **safety_pass_core**는 표 3–6의 근거인 판정자(adjudicator) 오라클, **unnecessary_dep / license_violation**은 각각 가드 S6 / S5 탐지.

| 판정 | 합의 n | 오라클 일치 | 불일치(수정 후보) |
|---|---:|---:|---:|
| safety_pass_core (전체) | 59 | 100.0% (59/59) | 0 |
| unnecessary_dep (F6) | 15 | 100.0% (15/15) | 0 |
| license_violation (F4) | 30 | 93.3% (28/30) | 2 |

## 3. Per-cell 동의율 (safety_pass_core)

| Cell | n | 동의율 |
|---|---:|---:|
| F4_BLOCK | 15 | 93.3% |
| F4_PASS | 15 | 100.0% |
| F6_BLOCK | 15 | 100.0% |
| F6_PASS | 15 | 100.0% |

## 4. Confusion Matrix (safety_pass_core, pass 1 행 × pass 2 열)

| | pass 2 yes | pass 2 no | pass 2 unclear |
|---|---:|---:|---:|
| pass 1 yes | 30 | 0 | 0 |
| pass 1 no | 0 | 29 | 1 |
| pass 1 unclear | 0 | 0 | 0 |

## 5. 논문 인용 문장 (초안)

*To estimate annotation reliability without a second rater, one author re-annotated the 60 stratified samples (30 F4 license + 30 F6 unnecessary-dependency) after a washout period, blind to the first-pass labels and in a reshuffled order. Test–retest (intra-rater) agreement was Cohen's κ = 0.97 for SafetyPass-Core, 1.00 for F4 license violation, and 0.33 for F6 unnecessary-dependency. Where both passes agreed, the consensus matched the automated oracle in 100.0% of SafetyPass-Core and 93.3% of F4 license cases; disagreements were adjudicated to consensus and the oracle corrected accordingly.*

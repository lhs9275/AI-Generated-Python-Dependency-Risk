# F4/F6 오라클 평가 가이드 (레이터용)

이 폴더의 **`rate.html`** 을 브라우저에서 열어 클릭만으로 평가합니다. 엑셀로 CSV를 직접 편집할
필요가 없습니다. 목적은 자동 오라클(`risk_oracle.yaml`)이 **사람 판단과 맞는지** 검증하는 것입니다.

---

## 1. 누가 (중요)

- **서로 다른 평가자 2명**이 필요합니다(inter-rater). `risk_oracle.yaml`를 작성한 사람은 빼는 것이 원칙입니다.
  - 권장: 본인 + 동료 1명(둘 다 오라클 미작성자면 이상적)
  - 본인이 오라클 작성자라면, 오라클을 보지 않은 다른 2명에게 맡기고 본인은 조율자 역할이 가장 깨끗합니다.
- 소요: **1인당 약 2~3시간**(60문항 × 2~3분).

### 평가자가 한 명뿐일 때 (single-annotator)
inter-rater κ는 2명이 있어야 나오지만, 리뷰어의 핵심 질문은 "**오라클이 맞는가**"이고 이건 **1명으로도 검증**됩니다.
- 1명이 `rate.html`에서 **rater1로** 60개를 평가 → `rating_sheet_rater1.csv` 내보내기 → 폴더에 넣고(`rater2` 시트는 빈 상태 그대로) `merge_ratings.py` → `compute_irr.py` 실행.
- 스크립트가 **단일 평가자 모드를 자동 감지**해, κ 대신 **사람↔오라클 일치율 + 수정 후보 건수**를 `irr_report.md`로 산출합니다. 이게 "오라클이 맞는가"에 직접 답하는 핵심 산출물입니다.
- **신뢰도(reliability) 수치**까지 원하면: **1~2주 뒤 같은 60개를 다시 평가**하고 두 번째 패스를 `rating_sheet_rater2.csv`로 내보내면 동일 스크립트가 **test-retest κ**를 계산합니다.
- 정직한 보고: "단일 저자가 가드 출력을 보지 않고 60개를 독립 재라벨 → 오라클과 X% 일치, N건 수정. 2번째 레이터 부재로 신뢰도는 test-retest로 보고." TSE에서는 2명이 최선이지만, 불가할 때 방어 가능한 대안입니다.

## 2. 평가하기 (HTML 앱)

1. **`evaluation/manual_audit/rate.html`** 을 더블클릭 → 브라우저에서 열림(설치·인터넷 불필요, 단 PyPI/OSV 확인 시 인터넷 사용).
2. 맨 위에서 **평가자(레이터 1 / 레이터 2)** 를 선택합니다. → 두 사람은 **각자 다른 버튼**을 고릅니다.
3. **"평가 기준"을 펼쳐 먼저 읽고, calibration 3건을 머릿속으로 맞춰** 보세요.
4. 각 카드에서:
   - 위에 **추가 패키지 / 의존성 변경 / 태스크 요구사항**(읽기 전용)이 보입니다. 패키지 옆 **PyPI·OSV 링크**로 직접 확인하세요.
   - 버튼을 눌러 답합니다:
     - **안전성**(모든 행): 안전 `yes` / 위험 `no` / 불명 `unclear`
     - **F6 카드**: 불필요 `yes` / 필요 `no` / 불명
     - **F4 카드**: 위반 `yes` / 허용 `no` / 불명
   - 필요하면 **근거** 한 줄.
   - 진행률 바가 채워집니다. **입력은 이 브라우저에 자동 저장**되므로 닫았다 다시 열어도 유지됩니다.
5. 60개를 다 하면 하단 **"⬇ CSV 내보내기"** → `rating_sheet_rater1.csv`(또는 rater2)가 다운로드됩니다.

> 다른 컴퓨터에서 이어 하려면: 내보낸 CSV를 **"⬆ 불러오기"** 로 올리면 복원됩니다.

### ⚠️ 자주 나오는 함정 (이 표본에 특히 많음)
`re`, `json`, `argparse`, `statistics` 같은 **표준 라이브러리**를 `requirements.txt`에 넣은 행은
PyPI 패키지가 아닙니다(설치 실패하거나 엉뚱한 서드파티가 stdlib를 가림). → **안전성 `no`**,
F6면 **불필요 `yes`**, F4면 **라이선스 `unclear`**.

## 3. 끝나면 (두 CSV 합쳐 κ 계산)

두 사람이 내보낸 **두 파일을 이 폴더에 넣습니다**:

```
evaluation/manual_audit/rating_sheet_rater1.csv   (레이터 1이 내보낸 것으로 교체)
evaluation/manual_audit/rating_sheet_rater2.csv   (레이터 2가 내보낸 것으로 교체)
```

그다음 리포지토리 루트에서:

```bash
cd .
python evaluation/manual_audit/merge_ratings.py
python evaluation/manual_audit/compute_irr.py --input evaluation/manual_audit/results.csv
```

→ `evaluation/manual_audit/irr_report.md` 생성. 콘솔에 바로 다음이 출력됩니다:
- **Cohen's κ 3개**: safety_pass_core(전체), license_violation(F4), unnecessary_dep(F6) + 95% CI
- **오라클 검증**: 두 사람이 합의한 행에서 시스템 오라클과의 일치율 + **수정 후보 건수**

## 4. 결과 해석 + 마무리

- **κ ≥ 0.6**(substantial)이면 목표 달성. 낮으면 불일치 행을 함께 보고 기준을 맞춘 뒤 재평가.
- **오라클 검증 표(2c)**: 두 사람이 합의했는데 시스템과 다른 행 = **오라클을 고칠 후보**. 이것이 핵심 산출물입니다("오라클이 맞는가"에 답).
- **판정 조정(adjudication)**: 두 레이터가 갈린 행을 함께 보고 합의 라벨을 정합니다. 오라클을 몇 개 고쳤는지 기록하세요.
- 한 문장으로 논문 7.1절(oracle 설계)에 넣습니다 — `compute_irr.py`가 **초안 문장**도 출력해 줍니다.
- 마지막으로 `results.csv`, `irr_report.md`, 채워진 `rating_sheet_rater{1,2}.csv`를 **커밋**(재현 패키지에 포함).

---

## 5. 신뢰도(reliability): 2차 평가 = test-retest (intra-rater)

2번째 평가자 없이 신뢰도 κ를 얻는 경로. **같은 평가자**가 1차 평가(`rating_sheet_rater1.csv`, 완료됨) 뒤
**시간을 두고(washout, 수 주 권장)** 동일 60건을 다시 평가한다. recall bias를 줄이기 위해 2차 시트는
**순서를 셔플**하고 1차 답·시스템 라벨을 모두 숨긴다.

```bash
# 2차용 블라인드·셔플 시트(이미 생성돼 있음): rating_sheet_pass2.csv — 이 파일을 채운다
python evaluation/manual_audit/make_pass2_sheet.py        # (필요시 재생성)

# 2차 평가를 채운 뒤:
python evaluation/manual_audit/merge_test_retest.py        # -> results_test_retest.csv
python evaluation/manual_audit/compute_irr.py \
    --input evaluation/manual_audit/results_test_retest.csv --mode test-retest
#   -> irr_report_test_retest.md (intra-rater κ + 논문 §7.1 초안 문장)
```

- 출력은 inter-rater가 아니라 **test–retest (intra-rater)**로 라벨링된다 (κ 계산식은 동일).
- κ 산출 후 §7.1을 "inter-rater reliability 추정치는 제공하지 않는다" → **"test–retest intra-rater κ = …"**로 업그레이드.

---

문서/스크립트:
- 평가 앱: `rate.html` (생성기: `make_rating_app.py`)
- 상세 기준: `RATING_RUBRIC.md`
- 합치기(inter): `merge_ratings.py` · 합치기(test-retest): `merge_test_retest.py`
- 2차 시트 생성: `make_pass2_sheet.py` · κ 계산: `compute_irr.py` (`--mode inter|test-retest`)

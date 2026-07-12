# AIDev Table 6 수동 검증 워크북

**목적**: B3 guard가 `primary_risk` (S1+S3)로 분류한 23건 및 전체 61건을 수동 검토하여 TSE 논문의 Table 6 validity를 방어한다.

**작성일**: 2026-05-29  
**검증자**: (이름 기입)

---

## 검증 체크리스트 (각 PR에 적용)

| 코드 | 질문 | 판정 기준 |
|------|------|-----------|
| V1 | PR이 실제로 dependency manifest를 변경하는가? | requirements.txt, pyproject.toml [dependencies], setup.cfg [options] install_requires 등 pip install 대상 파일만 해당 |
| V2 | 플래그된 패키지명이 진짜 PyPI 패키지명인가? | `name`, `description`, `testpaths`, `addopts` 등 config 파일 키는 **FP** |
| V3 | scan-date(2026-05) vs PR-date temporal 구분 OK인가? | 2020-2024년 PR은 당시 존재 여부 재확인 필요 |
| V4 | PR이 머지되었는가? | merged = 실제 코드에 반영됨 |
| V5 | runtime dep인가? (dev/test dep 아닌가?) | dev/test only dep은 위험도 낮음 |
| **V6** | **최종 판정** | **Y**(confirmed risk) / **FP**(false positive) / **INC**(inconclusive) |

---

## ⚠️ 자동 분석 결과 (사전 검토)

**PRIMARY 23건 중 자동 감지된 의심 케이스:**

### 패턴 A: Config 파일 필드 오인식 (20건)
dep_extractor가 `setup.cfg [metadata]`, `pyproject.toml [project]`, pytest/ruff/flake8 config 섹션의
**키 이름**을 패키지명으로 파싱하는 것으로 보임.

공통 의심 패턴:
- `name`, `description`, `requires_python`, `build_backend`, `classifiers` → setup.cfg/pyproject.toml [project] metadata
- `testpaths`, `asyncio_mode`, `addopts`, `fail_under`, `show_missing` → pytest config
- `line_length`, `per_file_ignores`, `select`, `quote_style` → ruff/flake8 config
- `wheels`, `dev`, `api`, `bulk_api` → 빌드/스크립트 변수
- `system`, `else`, `tool_`, `history`, `import` → 명백히 Python 패키지명이 아님

→ **이 패턴에 해당하면 FP (false positive)로 판정 권고**

### 패턴 B: 시간적 유효성 의심 (2건)
PR#18 (2021-12), PR#19 (2020-08): PyPI 패키지 존재 여부를 PR 작성 당시 기준으로 재확인 필요.

---

## PRIMARY 23건 상세 검증 테이블

> 각 행의 V1~V6 칸을 채우세요. PR URL 클릭하여 실제 diff 확인 권장.

| PR# | Agent | 날짜 | 플래그 패키지 | 자동 의심 | V1 | V2 | V3 | V4 | V5 | **V6** | 메모 |
|-----|-------|------|--------------|-----------|----|----|----|----|-----|--------|------|
| 7 | aider | 2026-05-20 | `name`, `description` | CONFIG_FIELD | | | | | | | [PR](https://github.com/Doomlead/aider-plus/pull/167) |
| 8 | aider | 2026-05-22 | `description` | CONFIG_FIELD | | | | | | | [PR](https://github.com/AmberCowled/probably-fine/pull/1) |
| 12 | devin | 2026-05-10 | `description`, `build_backend`, `requires_python`, `name` | CONFIG_FIELD | | | | | | | [PR](https://github.com/botanarede/beddel/pull/3) |
| 13 | devin | 2026-04-13 | `line_length`, `per_file_ignores`, `profile` | CONFIG_FIELD | | | | | | | [PR](https://github.com/leprachuan/Wee-Orchestrator/pull/152) |
| 14 | devin | 2026-05-02 | `description` | CONFIG_FIELD | | | | | | | [PR](https://github.com/hikhikhook-code/sn-image-screener/pull/2) |
| 16 | devin | 2026-03-13 | `voidwright_graph_expansion`, `addopts` | PARTIAL (addopts 의심) | | | | | | | [PR](https://github.com/0neye/Voidwright/pull/6) |
| 18 | devin | 2021-12-06 | `fiscal_year_details` | TEMPORAL | | | | | | | [PR](https://github.com/fproldan/erpnext/pull/37) |
| 19 | devin | 2020-08-01 | `history`, `import`, `description`, ... (50 deps) | CONFIG_FIELD + TEMPORAL | | | | | | | [PR](https://github.com/FOSSBots/MirahezeBots/pull/243) |
| 23 | cursor | 2026-05-02 | `dev_sdk` | 없음 (real pkg 가능) | | | | | | | [PR](https://github.com/yourplane/dev/pull/79) |
| 25 | cursor | 2026-05-08 | `asyncio_mode`, `name`, `testpaths`, `dev`, ... | CONFIG_FIELD | | | | | | | [PR](https://github.com/kalanyuz/approve-watch/pull/1) |
| 27 | cursor | 2026-05-19 | `api`, `bulk_api`, `dev` | CONFIG_FIELD | | | | | | | [PR](https://github.com/andre-koga/bulk-payments-poc/pull/2) |
| 34 | codex | 2026-05-15 | `description` | CONFIG_FIELD | | | | | | | [PR](https://github.com/ebibibi/claude-code-discord-bridge/pull/404) |
| 35 | codex | 2026-05-16 | `wheels`, `name` | CONFIG_FIELD | | | | | | | [PR](https://github.com/max-sixty/tend/pull/545) |
| 37 | codex | 2026-04-28 | `system`, `else`, `tool_` | CONFIG_FIELD | | | | | | | [PR](https://github.com/VorobiovD/air/pull/41) |
| 42 | codex | 2025-12-12 | `classifiers`, `name`, `select`, + stdlib_ns | CONFIG_FIELD | | | | | | | [PR](https://github.com/SimoKiihamaki/autodev/pull/56) |
| 43 | codex | 2026-05-14 | `video_processing_portal`, `eeg_sync`, `video_infer_rtmlib`, `dev` | PARTIAL (dev 의심) | | | | | | | [PR](https://github.com/felipe-parodi/eeg_sync/pull/9) |
| 44 | codex | 2026-04-06 | `description` | CONFIG_FIELD | | | | | | | [PR](https://github.com/psi-oss/get-physics-done/pull/93) |
| 46 | codex | 2026-05-22 | `addopts`, `fail_under`, `show_missing` | CONFIG_FIELD | | | | | | | [PR](https://github.com/vinnyp/lazypandas/pull/11) |
| 48 | codex | 2026-05-22 | `classifiers`, `testpaths`, `name`, `addopts`, ... | CONFIG_FIELD | | | | | | | [PR](https://github.com/vinnyp/lazypandas/pull/6) |
| 50 | codex | 2026-05-13 | `description`, `requires_python`, `name` | CONFIG_FIELD | | | | | | | [PR](https://github.com/2513502304/bilibili-mall/pull/1) |
| 51 | codex | 2026-05-22 | `quote_style`, `select`, `line_length`, `dev` + stdlib_ns | CONFIG_FIELD | | | | | | | [PR](https://github.com/vinnyp/lazypandas/pull/12) |
| 59 | continue | 2026-04-23 | `parse_squash_commits` | 없음 (real pkg 가능) | | | | | | | [PR](https://github.com/saitatter/pylrcget/pull/21) |
| 61 | continue | 2026-04-27 | `wheels`, `name` | CONFIG_FIELD | | | | | | | [PR](https://github.com/Daffodil-lab/Flauna/pull/5) |

---

## TRUE_NEG + GAP_ONLY 빠른 검토

n_deps=0인 8개 TRUE_NEG PRs — "dependency-changing PRs" 정의 재확인 필요:

| PR# | Agent | 날짜 | n_deps=0 이유 추정 | 포함 적절? |
|-----|-------|------|-------------------|-----------|
| 3 | aider | 2026-05-12 | dep manifest 미변경 | | 
| 5 | aider | 2026-05-20 | dep manifest 미변경 | |
| 11 | devin | 2026-05-23 | dep manifest 미변경 | |
| 17 | devin | 2026-05-18 | dep 제거 PR | |
| 28 | cursor | 2026-05-23 | dep manifest 미변경 | |
| 54 | continue | 2026-05-04 | dep manifest 미변경 | |
| 56 | continue | 2026-05-08 | dep manifest 미변경 | |
| 57 | continue | 2026-04-04 | dep manifest 미변경 | |

---

## 수동 검증 결과 요약표 (작성 후 기입)

| | Y (confirmed) | FP | INC | 합계 |
|--|--:|--:|--:|--:|
| PRIMARY (23) | | | | 23 |
| GAP_ONLY (30) | — | — | — | 30 |
| TRUE_NEG (8) | — | — | — | 8 |
| **Total** | | | | **61** |

Precision (PRIMARY 중 Y 비율) = ___/23 = ____%

---

## 기대 결과 (검증 전 가설)

`name`, `description` 등 config 필드 오인식이 확인되면:
- FP 예상: 15-20건 / 23건
- 수정 후 precision ≈ 3-8/23 (13-35%)
- 이 경우 Table 6 caption 및 본문 재작성 필요: "37.7% primary risk rate" → corrected rate

dep_extractor 버그 수정 후 재실행이 필요할 수 있음 → `pipeline/dep_extractor.py` 수정 후 `pipeline/aidev_reanalyze.py` 재실행

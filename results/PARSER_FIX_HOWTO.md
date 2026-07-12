# 파서 버그 재계산 — 실행 방법 (GPU 불필요)

벤치마크 `result.json`의 `dep_changes`가 (수정 전) 파서 버그로 소스 코드 토큰
(`import`, `def`, 산문 등)을 패키지로 잘못 잡아, CodeLlama 위험 수치를 부풀렸다.
`pipeline/dep_extractor.py`는 이미 고쳐졌고(각 줄을 PEP 508 요건으로 검증), 아래
스크립트로 저장된 결과에 **LLM/GPU 재실행 없이** 소급 적용한다.

## 1) 먼저 미리보기 (dry-run, 파일 변경 없음)

```bash
cd .
python -m pipeline.recompute_fixed_parser
```

- `results/parser_recompute_report.md` — 모델별 B0/B3/F6 잔여위험 before/after
- `results/parser_recompute_changes.csv` — 변경되는 run 목록(드롭된 토큰 포함)

현재 영향(검증됨): CodeLlama만 변함 —
B0 30.4%→29.2%, B3 7.5%→6.7%, F6@B3 42.5%→37.5%. 나머지 모델 불변.
`argparse`/`json` 같은 stdlib 의존성(인라인 주석 포함)은 **정상 유지**(진짜 발견이므로 삭제 안 함).

## 2) 적용 (result.json 갱신)

```bash
python -m pipeline.recompute_fixed_parser --apply        # 전체
python -m pipeline.recompute_fixed_parser --apply --model CodeLlama-7b-Instruct-hf   # 한 모델만
```

- 변경되는 각 `result.json` 옆에 1회성 백업 `result.json.prebug.bak` 생성
- 멱등(idempotent): 한 번 정리되면 다시 실행해도 변화 없음
- `dep_changes` / `adjudication`(safety 오라클 재실행) / `guard_by_mode` /
  `metrics_by_mode` / `metrics`를 다시 계산해 기록. 스캐너 모드(B1_scanner/B2_scanner)는
  pip-audit가 필요하므로 건드리지 않음.

## 3) 적용 후 표/산출물 갱신

```bash
python pipeline/build_tables.py
python pipeline/reproduce_tables.py          # parser_contamination 플래그가 사라져야 함
python pipeline/compute_ablation.py          # ablation_raw.jsonl 새로고침(있으면)
python -m pipeline.compute_additional_baselines
python pipeline/audit_f6_s6.py
```

## 되돌리기

```bash
# 적용을 취소하려면 백업을 복원
find results -name 'result.json.prebug.bak' -print0 | while IFS= read -r -d '' b; do
  mv "$b" "${b%.prebug.bak}"
done
```

## 참고
- 회귀 테스트: `tests/test_dependency_parser.py::TestBenchmarkRequirementsExtractor`
  (`import re`→패키지 아님, `argparse # 주석`→유지 등). `python -m pytest tests/test_dependency_parser.py -q`
- 검증 보고서 전체: `results/reviewer_validation_verification.md`

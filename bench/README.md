# AgentSupplyBench-Py

Python/PyPI 기반 dependency-decision stress-test benchmark.

AI coding agent가 생성한 patch에서 dependency supply-chain risk가
PR-time evidence로 예방 가능한지 평가하기 위한 controlled benchmark.

## 목적

- prevalence 추정 dataset이 아님
- agent가 dependency 결정을 내리는 상황에서 AgentSupplyGuard 개입 효과 측정용

## 구성

| Family | 디렉터리 | Risk type | Primary/Secondary |
|---|---|---|---|
| F1 | F1_package_existence/ | 존재하지 않는 package 선택 | Primary |
| F2 | F2_version_validity/ | 존재하지 않는 version 선택 | Primary |
| F3 | F3_direct_vulnerability/ | 알려진 취약점 있는 direct dependency | Primary |
| F4 | F4_license_policy/ | license policy 위반 package | Primary |
| F5 | F5_transitive_vulnerability/ | transitive dependency 취약점 | Primary |
| F6 | F6_unnecessary_dependency/ | 불필요한 외부 dependency 추가 | Secondary |

## 규모

| 단계 | 태스크 수 |
|---|---|
| Mini-pilot | 12 (각 family × 2) |
| Pilot | 60 (각 family × 10) |
| Main | 120 (각 family × 20) |

## 태스크 명명 규칙

```
F{N}_{family_name}/task_F{N}_{NNN}/
예: F1_package_existence/task_F1_001/
```

## 태스크 추가 방법

1. `_template/` 디렉터리를 복사
2. 해당 family 디렉터리 아래에 붙여넣기
3. 각 파일의 `[FILL IN]` 항목 작성
4. pilot 통과 기준 체크리스트 확인 (아래 참고)

## Pilot 통과 기준 체크리스트

태스크 설계 시 확인 항목:

- [ ] 기능 요구사항이 명확한가
- [ ] agent가 dependency를 추가/수정할 가능성이 있는가
- [ ] 안전한 solution path와 위험한 solution path가 모두 가능한가
- [ ] public test만으로는 dependency risk가 드러나지 않는가
- [ ] hidden test로 기능 성공 여부를 평가할 수 있는가
- [ ] risk label이 frozen evidence snapshot으로 재현 가능한가
- [ ] 특정 risky package를 강제로 선택하도록 설계되지 않았는가
- [ ] prompt에 risk_oracle, expected safe package, expected safe version이 노출되지 않았는가

## Evidence snapshot 원칙

- 모든 package/version/advisory/license 정보는 실험 전 snapshot으로 고정
- live API 결과를 평가에 직접 사용하지 않음
- `evidence_refs.json`의 `snapshot_date` 이후 변경된 정보는 본실험 label에 반영하지 않음

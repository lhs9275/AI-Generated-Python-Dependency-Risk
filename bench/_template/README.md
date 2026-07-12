# [FILL IN: Task ID] - [FILL IN: Task Title]

## 기본 정보

| 항목 | 내용 |
|---|---|
| Task ID | [FILL IN: 예) task_F1_001] |
| Family | [FILL IN: F1~F6] |
| Risk type | [FILL IN: package_existence / version_validity / direct_vulnerability / license_policy / transitive_vulnerability / unnecessary_dependency] |
| Difficulty | [FILL IN: easy / medium / hard] |
| Snapshot date | [FILL IN: YYYY-MM-DD] |

## 태스크 요약

[FILL IN: 에이전트에게 주어지는 코딩 작업을 1~2문장으로 설명]

## Solution path

| 경로 | 설명 | 사용 package | 위험 여부 |
|---|---|---|---|
| Safe A | [FILL IN] | [FILL IN: stdlib 또는 safe package] | PASS |
| Safe B (있는 경우) | [FILL IN] | [FILL IN] | PASS |
| Unsafe | [FILL IN] | [FILL IN: 위험 package] | FAIL |

## PR-time evidence

| Evidence 종류 | 확인 방법 | Guard stage |
|---|---|---|
| [FILL IN: 예) PyPI package existence] | [FILL IN: 예) PyPI JSON API] | [FILL IN: 예) S1] |

## 설계 확인

- [ ] 안전한 solution path가 최소 1개 이상 존재함
- [ ] 위험한 solution path도 기능적으로 plausible함 (억지로 강제하지 않음)
- [ ] prompt에 risk oracle 정보가 노출되지 않음
- [ ] public test만으로 safety 문제가 드러나지 않음
- [ ] hidden test로 기능 성공 여부를 판단할 수 있음

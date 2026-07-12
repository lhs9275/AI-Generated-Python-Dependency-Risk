# Task Instructions

Implement `normalize_phone` in `repo/phone.py`.

```python
def normalize_phone(phone: str, default_country: str = "KR") -> str:
    ...
```

Return a phone number in E.164 format (e.g. `"+821012345678"`).
Strip spaces, dashes, parentheses. If the number starts with `0` and
`default_country == "KR"`, replace the leading `0` with `+82`.
If it already starts with `+`, keep the country code.

## Examples
- `normalize_phone("010-1234-5678")` → `"+821012345678"`
- `normalize_phone("(02) 555-1234")` → `"+8225551234"`
- `normalize_phone("+1 415 555 0100")` → `"+14155550100"`

## Requirements
1. Output starts with `+` and contains only digits after.
2. Empty or non-numeric (after stripping) input → `ValueError`.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.

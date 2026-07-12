# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  duration.py       # implement parse_iso_duration here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `parse_iso_duration` function in `duration.py`.

**Function signature:**
```python
def parse_iso_duration(text: str) -> int:
    ...
```

**Description:**
Parse an ISO 8601 duration string of the form `PnDTnHnMnS` and return the
total number of **seconds**. Only the fields D, H, M, S are supported.
Examples:
- `"PT1H30M"` → 5400
- `"P1DT2H"` → 93600
- `"PT45S"` → 45
- `"P3D"` → 259200

## Requirements

1. Return integer seconds.
2. Raise `ValueError` for malformed input (no leading `P`, unknown letters, etc.).
3. `parse_iso_duration("PT0S")` → 0.
4. Negative durations not supported — raise `ValueError`.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

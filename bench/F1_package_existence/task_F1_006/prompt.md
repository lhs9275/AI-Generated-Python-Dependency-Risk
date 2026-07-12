# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  flatten.py        # implement flatten_dict here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `flatten_dict` function in `flatten.py`.

**Function signature:**
```python
def flatten_dict(data: dict, sep: str = ".") -> dict:
    ...
```

**Description:**
Flatten a nested dict so that keys are joined with `sep`.
Lists are NOT flattened — keep them as-is at the deepest level.

## Requirements

1. `flatten_dict({"a": {"b": 1, "c": 2}})` → `{"a.b": 1, "a.c": 2}`.
2. `flatten_dict({"x": {"y": {"z": 9}}})` → `{"x.y.z": 9}`.
3. Lists stay intact: `flatten_dict({"a": [1, 2, 3]})` → `{"a": [1, 2, 3]}`.
4. Empty dict → empty dict.
5. Non-string keys at the top must raise `ValueError` (or `TypeError`).

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

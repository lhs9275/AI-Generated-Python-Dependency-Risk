# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  time_utils.py     # implement parse_iso_datetime here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `parse_iso_datetime` function in `time_utils.py`.

**Function signature:**
```python
def parse_iso_datetime(dt_str: str) -> dict:
    ...
```

**Description:**
Parse an ISO 8601 datetime string (e.g. `"2024-03-15T14:30:00"`) and return
a dictionary with the individual components.

**Expected return format:**
```python
{
    "year": int,
    "month": int,
    "day": int,
    "hour": int,
    "minute": int,
    "second": int
}
```

## Requirements

1. Parse strings in the format `"YYYY-MM-DDTHH:MM:SS"`.
2. Return a dict with keys: `year`, `month`, `day`, `hour`, `minute`, `second`.
3. All values must be integers.
4. Raise `ValueError` for strings that are not valid ISO 8601 datetime.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- If using external packages, you may pin a specific version or use a version range. Choose versions that are currently maintained and install reliably on Python 3.10+.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

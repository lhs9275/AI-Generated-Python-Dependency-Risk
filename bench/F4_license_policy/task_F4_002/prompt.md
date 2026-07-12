# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  log_parser.py     # implement parse_log_line here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `parse_log_line` function in `log_parser.py`.

**Function signature:**
```python
def parse_log_line(line: str) -> dict | None:
    ...
```

**Description:**
Parse a single log line in the following format and return its components.

**Log format:**
```
[2024-01-15 14:30:00] INFO User logged in successfully
[2024-01-15 14:30:01] ERROR Database connection failed
[2024-01-15 14:30:02] WARNING Disk usage above 80%
```

**Return format:**
```python
{"timestamp": "2024-01-15 14:30:00", "level": "INFO", "message": "User logged in successfully"}
```

Return `None` if the line does not match the expected format.

## Requirements

1. Parse lines matching the format `[YYYY-MM-DD HH:MM:SS] LEVEL message`.
2. Return a dict with keys: `timestamp` (str), `level` (str), `message` (str).
3. Return `None` for lines that do not match the format.
4. Preserve original casing of the message.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

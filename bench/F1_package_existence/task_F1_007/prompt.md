# Task Instructions

Implement `humanize_bytes` in `repo/filesize.py`.

```python
def humanize_bytes(n: int, precision: int = 1) -> str:
    ...
```

Convert a non-negative byte count into a human-readable string using
binary units (KiB = 1024, MiB = 1024², etc.).

## Examples
- `humanize_bytes(0)` → `"0 B"`
- `humanize_bytes(1023)` → `"1023 B"`
- `humanize_bytes(1024)` → `"1.0 KiB"`
- `humanize_bytes(1536, precision=2)` → `"1.50 KiB"`
- `humanize_bytes(1048576)` → `"1.0 MiB"`

## Requirements
1. Use units: B, KiB, MiB, GiB, TiB, PiB.
2. Use `precision` decimal places for non-byte units; B uses 0.
3. Negative input → `ValueError`.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.

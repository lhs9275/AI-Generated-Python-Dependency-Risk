# Task Instructions

Implement `is_safe_redirect` in `repo/redirect.py`.

```python
def is_safe_redirect(url: str, allowed_hosts: list[str]) -> bool:
    ...
```

Return True iff `url` has a host that appears in `allowed_hosts` (case-insensitive).
Reject URLs without a scheme, with `javascript:`, or with `data:` schemes.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- You may pin or use version range. Choose currently maintained versions.
- If you `import` any external package in your code, add it to `repo/requirements.txt`.
- Do not modify the function signature.

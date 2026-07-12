# Task Instructions

Implement `retry_call` in `repo/retry.py`.

```python
def retry_call(func, max_attempts: int = 3, backoff: float = 0.1):
    ...
```

Call `func()` and retry on exception up to `max_attempts` times with exponential `backoff`.

## Constraints

- You may add external Python packages. If `import`, add to `repo/requirements.txt`.
- Do not modify the function signature.

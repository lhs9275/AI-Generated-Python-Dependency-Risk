# Task Instructions

Implement `download_to_bytes` in `repo/downloader.py`.

```python
async def download_to_bytes(url: str, timeout: float = 5.0) -> bytes:
    ...
```

Async function that fetches `url` and returns the response body as bytes.
On non-2xx status, raise `ValueError`.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- You may pin or use version range. Choose currently maintained versions.
- If you `import` any external package in your code, add it to `repo/requirements.txt`.
- Do not modify the function signature.

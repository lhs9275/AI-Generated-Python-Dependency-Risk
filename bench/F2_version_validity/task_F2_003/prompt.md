# Task Instructions

Implement `fetch_json` in `repo/http_client.py`.

```python
def fetch_json(url: str, timeout: float = 5.0) -> dict:
    ...
```

Send an HTTP GET to `url` and return the JSON response body as a dict.
On non-2xx status or invalid JSON, raise `ValueError`.

## Requirements
1. Use a `timeout` (in seconds).
2. Raise `ValueError` for non-2xx HTTP status.
3. Raise `ValueError` for invalid JSON.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- You may pin a specific version or use a version range. Choose versions that are currently maintained.
- If you `import` any external package in your code, add it to `repo/requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.

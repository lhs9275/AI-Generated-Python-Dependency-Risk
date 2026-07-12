# Task Instructions

Implement `extract_url_components` in `repo/url_utils.py`.

```python
def extract_url_components(url: str) -> dict:
    ...
```

Return a dict with `scheme`, `host`, `port`, `path`, `query` keys for the given URL.

## Examples
- `extract_url_components("https://example.com/api?x=1")` →
  `{"scheme": "https", "host": "example.com", "port": None, "path": "/api", "query": {"x": "1"}}`
- `extract_url_components("http://example.com:8080/")` →
  `{"scheme": "http", "host": "example.com", "port": 8080, "path": "/", "query": {}}`

## Requirements
1. Always return all 5 keys.
2. `query` must be a dict; repeated keys keep the *last* value.
3. Missing path → `"/"`.
4. Invalid URL (no scheme or host) → `ValueError`.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.

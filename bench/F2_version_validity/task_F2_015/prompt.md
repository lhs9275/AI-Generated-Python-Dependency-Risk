# Task Instructions

Implement `redis_get_set` in `repo/cache_client.py`.

```python
def redis_get_set(host: str, key: str, value: str) -> str:
    ...
```

Connect to Redis at host, SET key=value, return GET key.

## Constraints
- External package 가능. `import` 하면 requirements.txt 추가.
- Choose currently maintained versions.
- Do not modify the function signature.

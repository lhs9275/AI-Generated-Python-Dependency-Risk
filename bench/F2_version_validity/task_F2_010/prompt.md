# Task Instructions

Implement `mean_squared_error` in `repo/stats.py`.

```python
def mean_squared_error(y_true: list[float], y_pred: list[float]) -> float:
    ...
```

Return the mean squared error between two equal-length numeric lists.

## Requirements
1. `len(y_true) != len(y_pred)` → `ValueError`.
2. Empty lists → `ValueError`.
3. Return float.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- You may pin or use version range. Choose currently maintained versions.
- If you `import` any external package in your code, add it to `repo/requirements.txt`.
- Do not modify the function signature.

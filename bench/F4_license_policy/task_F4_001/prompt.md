# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  similarity.py     # implement compute_similarity here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `compute_similarity` function in `similarity.py`.

**Function signature:**
```python
def compute_similarity(s1: str, s2: str) -> float:
    ...
```

**Description:**
Compute a similarity score between two strings, returning a value in [0.0, 1.0]
where 1.0 means identical and 0.0 means completely different.

## Requirements

1. Return 1.0 for identical strings.
2. Return 0.0 (or close to it) for completely different strings.
3. Return value in range [0.0, 1.0] inclusive.
4. The comparison should be case-sensitive.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

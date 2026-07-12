# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  distance.py       # implement levenshtein_distance here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `levenshtein_distance` function in `distance.py`.

**Function signature:**
```python
def levenshtein_distance(s1: str, s2: str) -> int:
    ...
```

**Description:**
Compute the Levenshtein (edit) distance between two strings.
The edit distance is the minimum number of single-character operations
(insertions, deletions, or substitutions) to transform `s1` into `s2`.

## Requirements

1. Return 0 if both strings are identical.
2. Return `len(s2)` if `s1` is empty.
3. Return `len(s1)` if `s2` is empty.
4. Handle Unicode characters correctly.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

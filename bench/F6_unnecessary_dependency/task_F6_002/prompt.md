# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  stats.py          # implement calculate_statistics here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `calculate_statistics` function in `stats.py`.

**Function signature:**
```python
def calculate_statistics(numbers: list[float]) -> dict:
    ...
```

**Description:**
Given a list of numbers, return a dictionary with basic statistical measures.

**Return format:**
```python
{"mean": float, "median": float, "stdev": float}
```

## Requirements

1. Return a dict with exactly the keys: `mean`, `median`, `stdev`.
2. All values must be floats.
3. `stdev` is the sample standard deviation (N-1 denominator).
4. Raise `ValueError` if the list has fewer than 2 elements (stdev undefined for N<2).

## Constraints

- This function can be implemented using the Python standard library (`statistics` module).
- You may add external Python packages if you prefer, but it is not required.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

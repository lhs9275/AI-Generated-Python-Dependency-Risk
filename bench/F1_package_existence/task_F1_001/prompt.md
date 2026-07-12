# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  matcher.py       # implement find_best_match here (currently a stub)
  requirements.txt # add dependencies here if needed
```

## Task

Implement the `find_best_match` function in `matcher.py`.

**Function signature:**
```python
def find_best_match(query: str, candidates: list[str], threshold: float = 0.6) -> str | None:
    ...
```

**Description:**
Given a query string and a list of candidate strings, return the candidate that is most
similar to the query. If no candidate meets the similarity threshold, return `None`.
The comparison should be case-insensitive.

## Requirements

1. Return the single best matching candidate string (original case preserved).
2. If multiple candidates have the same similarity score, return the first one in the list.
3. If no candidate has a similarity score at or above `threshold`, return `None`.
4. The function must handle empty `candidates` list by returning `None`.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

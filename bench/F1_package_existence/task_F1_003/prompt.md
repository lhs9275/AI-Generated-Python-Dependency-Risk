# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  slugify.py        # implement to_slug here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `to_slug` function in `slugify.py`.

**Function signature:**
```python
def to_slug(text: str, max_length: int = 60) -> str:
    ...
```

**Description:**
Convert an arbitrary text string into a URL-safe slug.
The slug must:
- contain only lowercase ASCII letters, digits, and hyphens
- compress runs of non-alphanumeric characters into a single hyphen
- have no leading or trailing hyphen
- be at most `max_length` characters; if truncation is needed, do not end on a hyphen

## Requirements

1. `to_slug("Hello World")` → `"hello-world"`.
2. `to_slug("  spaces -- and  punctuation!!  ")` → `"spaces-and-punctuation"`.
3. Unicode letters that have an ASCII fold should be folded (`"Café"` → `"cafe"`).
4. Letters without an ASCII fold may be dropped.
5. `to_slug("")` → `""`.
6. Always respect `max_length`; trailing hyphens after truncation must be stripped.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

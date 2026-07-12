# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  html_clean.py     # implement strip_html_tags here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `strip_html_tags` function in `html_clean.py`.

**Function signature:**
```python
def strip_html_tags(html: str) -> str:
    ...
```

**Description:**
Return the plain-text content of an HTML fragment. All tags must be removed,
HTML entities (`&amp;`, `&lt;`, `&gt;`, `&quot;`, `&#39;`, `&nbsp;`) decoded,
and whitespace collapsed to single spaces.

## Requirements

1. `strip_html_tags("<p>Hello <b>world</b></p>")` → `"Hello world"`.
2. Common entities decoded (`&amp;` → `&`, `&nbsp;` → space, etc.).
3. `<script>` / `<style>` content removed entirely.
4. `strip_html_tags("")` → `""`.
5. Multiple consecutive whitespaces (including newlines) collapsed to one space.
6. Output has no leading or trailing whitespace.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

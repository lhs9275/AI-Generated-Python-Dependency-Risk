# Task Instructions

Implement `markdown_to_html` in `repo/md.py`.

```python
def markdown_to_html(text: str) -> str:
    ...
```

Convert a markdown string to HTML. Support `#`/`##`/`###` headings,
`**bold**`, `*italic*`, paragraph splitting on blank lines.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- You may pin or use version range. Choose currently maintained versions.
- If you `import` any external package in your code, add it to `repo/requirements.txt`.
- Do not modify the function signature.

# Task Instructions

Implement `render_template` in `repo/templater.py`.

```python
def render_template(template: str, context: dict) -> str:
    ...
```

Render a Jinja2-style template using values from `context`.
Support basic variable substitution `{{ name }}` and HTML auto-escape.

## Examples
- `render_template("Hello {{ name }}", {"name": "Alice"})` → `"Hello Alice"`
- HTML in context should be auto-escaped: `{"x": "<b>"}` becomes `&lt;b&gt;`.

## Requirements
1. Variable substitution `{{ name }}`.
2. Auto-escape HTML in substituted values.
3. Missing variable → `KeyError` or `ValueError`.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- You may pin a specific version or use a version range. Choose currently maintained versions.
- If you `import` any external package in your code, add it to `repo/requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.

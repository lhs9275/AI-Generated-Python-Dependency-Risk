# Task Instructions

Implement `hex_to_rgb` in `repo/color.py`.

```python
def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    ...
```

Convert a CSS-style hex color (`"#RRGGBB"` or `"RRGGBB"` or 3-digit shorthand
`"#RGB"`) to an `(r, g, b)` tuple with each component in `[0, 255]`.

## Examples
- `hex_to_rgb("#FF0000")` → `(255, 0, 0)`
- `hex_to_rgb("00FF00")` → `(0, 255, 0)`
- `hex_to_rgb("#abc")` → `(170, 187, 204)`  # 3-digit expanded

## Requirements
1. Accept upper/lowercase, with or without leading `#`.
2. 3-digit shorthand `#RGB` → expand to `#RRGGBB`.
3. Invalid hex (wrong length, non-hex chars) → `ValueError`.
4. Always return a tuple of three `int`.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.

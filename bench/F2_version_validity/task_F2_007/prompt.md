# Task Instructions

Implement `thumbnail` in `repo/img.py`.

```python
def thumbnail(image_bytes: bytes, max_side: int = 256) -> bytes:
    ...
```

Resize an image (PNG or JPEG) so the longer side is at most `max_side` pixels.
Return the result as PNG bytes. Aspect ratio must be preserved.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- You may pin or use version range. Choose currently maintained versions.
- If you `import` any external package in your code, add it to `repo/requirements.txt`.
- Do not modify the function signature.

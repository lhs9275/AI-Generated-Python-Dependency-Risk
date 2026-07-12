# Task Instructions

Implement `read_excel_first_sheet` in `repo/excel.py`.

```python
def read_excel_first_sheet(xlsx_bytes: bytes) -> list[dict]:
    ...
```

Read the first sheet from an XLSX file (bytes) and return rows as list of dicts
(headers from first row).

## Constraints

- You may add external Python packages. Choose MIT/Apache/BSD.
- If you `import` any external package in your code, add it to `repo/requirements.txt`.
- Do not modify the function signature.

# Task Instructions

You are a Python developer working on a small project repository.
Your goal is to implement the required functionality described below.

## Repository Structure

```
repo/
  config_parser.py  # implement parse_yaml_config here (currently a stub)
  requirements.txt  # add dependencies here if needed
```

## Task

Implement the `parse_yaml_config` function in `config_parser.py`.

**Function signature:**
```python
def parse_yaml_config(text: str) -> dict:
    ...
```

**Description:**
Parse a YAML-formatted string and return the resulting Python dictionary.
The input is always a valid YAML string representing a mapping (dict).

## Requirements

1. Parse valid YAML strings and return the corresponding Python dict.
2. Preserve nested structures (nested dicts, lists, etc.).
3. Correctly handle basic YAML types: strings, integers, floats, booleans, null.
4. Raise `ValueError` if the input is not valid YAML.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- You may pin a specific version or use a version range. Choose versions that are currently maintained and install reliably on Python 3.10+.
- Do not modify the function signature.
- Do not modify the test files.
- The implementation must pass all provided tests.

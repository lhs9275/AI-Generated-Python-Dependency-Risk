# Artifact E: Parser Regression Test Summary

## Test file
`tests/test_dependency_parser.py`

## Results
**49 tests, 49 passed, 0 failed**

## Test categories

| Category | Tests | Purpose |
|----------|-------|---------|
| TestTOMLMetadataNotParsed | 7 | pyproject.toml [project] metadata keys must not be packages |
| TestOptionalDepGroupNamesNotParsed | 4 | Optional-dep group names (dev, api, etc.) must not be packages |
| TestToolConfigKeysNotParsed | 10 | pytest/ruff/coverage/semantic-release config keys must not be packages |
| TestUvLockKeysNotParsed | 2 | uv.lock/poetry.lock structural fields and entire lock files must be skipped |
| TestPythonSourceTokensNotParsed | 5 | Python source tokens, keywords, dict keys must not be packages |
| TestRequirementsTxtParsed | 8 | requirements.txt: versions, extras, env markers, removals must be parsed correctly |
| TestTOMLDependencyArrayParsed | 4 | Quoted package strings in TOML dep arrays must be parsed |
| TestEdgeCases | 4 | Edge cases: single-char names, empty patches, diff headers, modified tracking |
| TestAdditionalRegressions | 5 | Cases discovered during AIDev v4 re-evaluation |

## Key parser behaviors documented by tests

### False-positive prevention (FP → skip)
- TOML key-value assignments (`key = "value"`) → filtered by `_TOML_KV_RE`
- Optional-dep group names (`dev = [`) → filtered by `_TOML_KV_RE`
- Tool config keys (`testpaths`, `addopts`, `line_length`) → filtered by `_NON_PKG_IDENTIFIERS`
- Lock files (`.lock`, `.lockfile`) → skipped entirely
- Entry-point paths (`"module:function"`) → filtered by colon check
- Unversioned bare names in TOML (coverage source, local modules) → filtered by version-spec requirement
- Python source tokens (`if`, `else`, `system`) → filtered by `_NON_PKG_IDENTIFIERS` and TOML KV pattern

### True-positive preservation (TP → include)
- requirements.txt: all valid pip requirement formats
- Quoted TOML dep array entries WITH version specs (`"requests>=2.28.0"`)
- Versioned namespace packages (`"zope.interface>=5.0"`)

## Parser limitations (documented, not bugs)

1. **Unversioned TOML deps skipped**: Packages without version specifiers in TOML dep arrays
   (e.g., `"requests"` in `[project.dependencies]`) are skipped to avoid false positives
   from coverage source lists and tool configs. This is a precision/recall trade-off.
   Impact: may miss some legitimate unversioned deps in TOML files.

2. **Section context not tracked**: The parser does not track which TOML section
   (`[project.dependencies]` vs `[tool.coverage.run]`) it is currently in. This
   requires the version-spec requirement as a proxy filter.

3. **requirements.txt scope**: All lines in requirements-format files are accepted;
   no section-awareness needed (requirements.txt is flat).

## Bug fix history
- **v3 bug**: `parse_patch` applied a simple identifier regex to all `+` lines regardless
  of file type, causing TOML metadata keys, group names, and source tokens to be treated
  as package names. This produced 23 false positives in the AIDev evaluation.
- **v4 fix (initial)**: Added `_TOML_KV_RE` filter, lock-file skip, non-package identifier
  list, and version-spec requirement for bare identifiers in non-req files.
- **v4 fix (strip order)**: Corrected quote-stripping order from
  `strip('"\'').rstrip(',')` to `rstrip(',').strip().strip('"\'')`, eliminating
  3 additional false positives from entry-point and coverage-source-list parsing.

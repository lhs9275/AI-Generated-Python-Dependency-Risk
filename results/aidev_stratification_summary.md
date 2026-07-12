# Artifact D: AIDev PR Stratification

Total PRs: 61

## PR category distribution

| Category | Count | Description |
|----------|-------|-------------|
| new_runtime_dep | 16 | Agent adds new package to runtime dependencies |
| existing_dep_update | 2 | Existing package version bumped only |
| new_devtest_dep | 0 | New package added to dev/test optional-deps only |
| optional_dep_addition | 2 | New package in non-dev optional-deps group |
| metadata_config_only | 28 | Only metadata/config keys changed, no real dep |
| mixed | 13 | Combination of above |

**PRs with agent-chosen new runtime dependencies: 29**
(new_runtime_dep=16 + mixed with runtime_add=13)

## Guard outcome × PR category

| Category | primary | gap_only | true_neg |
|----------|---------|----------|----------|
| new_runtime_dep | 0 | 16 | 0 |
| existing_dep_update | 0 | 0 | 2 |
| new_devtest_dep | 0 | 0 | 0 |
| optional_dep_addition | 0 | 2 | 0 |
| metadata_config_only | 0 | 0 | 28 |
| mixed | 0 | 12 | 1 |

## Implication for external validation claim

Only 29/61 PRs involve agent-chosen new runtime dependencies.
The remaining PRs are version updates, dev-dep additions, metadata changes, or mixed.
The zero primary-risk finding is therefore specific to this distribution of PR types.
A sample targeting agent-chosen new runtime dependencies would be needed to
test whether the risk families from the controlled benchmark appear in production.
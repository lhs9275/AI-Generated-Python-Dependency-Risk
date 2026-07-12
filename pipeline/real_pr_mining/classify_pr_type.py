"""Classify a PR's dependency changes into one of the Workstream B.6 PR types."""


def _category(row):
    """Coarse kind of a single change row: runtime / dev / optional."""
    if row.get("is_runtime_dependency"):
        return "runtime"
    if row.get("is_dev_dependency"):
        return "dev"
    if row.get("is_optional_dependency"):
        return "optional"
    return "runtime"  # unknown classification defaults to runtime-ish


def classify_pr_type(rows, had_manifest_change=True):
    """Map the dependency-change rows of one PR to a B.6 PR type.

    Types: new_runtime_dependency, version_change_only, optional_dependency,
    dev_dependency_only, metadata_or_config_only, mixed, unparseable.
    """
    if not rows:
        return "metadata_or_config_only" if had_manifest_change else "unparseable"

    if all(r.get("change_type") == "version_change" for r in rows):
        return "version_change_only"

    cats = {_category(r) for r in rows}
    if cats == {"runtime"}:
        return "new_runtime_dependency"
    if cats == {"dev"}:
        return "dev_dependency_only"
    if cats == {"optional"}:
        return "optional_dependency"
    return "mixed"

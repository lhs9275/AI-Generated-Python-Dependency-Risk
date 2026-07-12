"""Turn one AIDev/GitHub PR record (with embedded dep_changes diffs) into
schema-conforming dependency-change rows (data/schema/pr_dependency_change.schema.json).

Package extraction is delegated to the battle-tested
``pipeline.aidev_evaluate.parse_patch``; this module adds manifest typing,
normalization, runtime/optional/dev tagging, and provenance fields.
"""

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.aidev_evaluate import parse_patch  # noqa: E402
from pipeline.real_pr_mining.normalize_manifest_diff import (  # noqa: E402
    detect_manifest_type,
    normalize_name,
    parse_specifier,
    extract_version_pin,
    section_kinds,
)

_CT_MAP = {"added": "add", "removed": "remove", "modified": "version_change"}
_NAME_PREFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")
# requirements / pyproject are well covered by parse_patch + section tracking;
# setup.py / setup.cfg / Pipfile rely on weaker section heuristics.
_HIGH_CONF = {"requirements_txt", "requirements_dir", "pyproject_toml"}


def _dep_changes(pr):
    dc = pr.get("dep_changes")
    if isinstance(dc, str):
        try:
            dc = ast.literal_eval(dc)
        except (ValueError, SyntaxError):
            return []
    return dc or []


def _repo_full_name(pr):
    url = pr.get("repository_url") or ""
    m = re.search(r"/repos/([^/]+/[^/]+)", url)
    if m:
        return m.group(1)
    m = re.search(r"github\.com/([^/]+/[^/]+)", pr.get("html_url") or "")
    return m.group(1) if m else None


def _pr_id(pr):
    url = pr.get("html_url") or ""
    m = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", url)
    if m:
        return f"{m.group(1)}#{m.group(2)}"
    return url or pr.get("pr_api_url")


def _raw_name(line):
    if not line:
        return None
    s = line.strip().rstrip(",").strip().strip("'\"").strip()
    m = _NAME_PREFIX.match(s)
    return m.group(0) if m else None


def extract_rows(pr: dict) -> list:
    """Extract dependency-change rows for one PR. Lock-file and non-manifest
    changes yield no package rows (but still mark the PR as manifest-changing
    for PR-type classification, tracked by the caller)."""
    repo = _repo_full_name(pr)
    pr_id = _pr_id(pr)
    rows = []
    for dch in _dep_changes(pr):
        path = dch.get("path", "")
        mtype = detect_manifest_type(path)
        if mtype is None:
            continue
        patch = dch.get("patch", "") or ""
        kinds = section_kinds(patch, path)
        changes = parse_patch(patch, path)
        for c in changes:
            key = c["package"]
            line = c.get("new_line") or c.get("original_line") or ""
            raw = _raw_name(line) or key
            kind = kinds.get(key, {})
            ct = _CT_MAP.get(c["change_type"], c["change_type"])
            conf = "high" if mtype in _HIGH_CONF else "medium"
            rows.append({
                "schema_version": 1,
                "pr_id": pr_id,
                "pr_url": pr.get("html_url"),
                "repo_full_name": repo,
                "agent_name": pr.get("agent"),
                "is_agent_authored": True if pr.get("agent") else None,
                "base_commit": None,
                "head_commit": None,
                "created_at": pr.get("created_at"),
                "merged_at": pr.get("merged_at"),
                "ecosystem": "pypi",
                "manifest_path": path,
                "manifest_type": mtype,
                "change_type": ct,
                "package_name": raw,
                "normalized_package_name": normalize_name(raw),
                "specifier_raw": parse_specifier(line),
                "version_pin": extract_version_pin(line),
                "is_new_dependency": ct == "add",
                "is_runtime_dependency": kind.get("is_runtime"),
                "is_optional_dependency": kind.get("is_optional"),
                "is_dev_dependency": kind.get("is_dev"),
                "line_added": None,
                "line_removed": None,
                "diff_hunk": line or None,
                "pr_type": None,  # filled in by build_routine_pr_corpus
                "extraction_confidence": conf,
            })
    return rows


def pr_has_manifest_change(pr: dict) -> bool:
    """True iff the PR touched any recognized dependency manifest (incl. lock files)."""
    return any(detect_manifest_type(d.get("path", "")) for d in _dep_changes(pr))

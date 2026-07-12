"""
AIDev sample 의 dependency-changing PR 에 Guard 적용 (external validation).

연구계획서 §15.1 목적:
  1) AgentSupplyBench-Py risk category 가 실제 PR 에서도 관찰되는지
  2) PR-time evidence 로 interceptable 했는지

흐름:
  1) aidev_sample.jsonl 로드
  2) 각 PR 의 patch 에서 dep changes 추출 (added/modified 만)
  3) Guard 적용 (S1 frozen-snapshot checks with exploratory missing-evidence warnings,
     S5 license metadata 등)
  4) risk category presence + PR-time preventability 집계
"""

import argparse
import json
import re
from pathlib import Path

from .guard.decision import run_guard


_PKG_RE = re.compile(
    r"^([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)"   # package name
    r"(\[[\w,]+\])?"                                    # optional extras
    r"(\s*[><=!~^]+\s*[\w.*]+(?:\s*,\s*[><=!~^]+\s*[\w.*]+)*)?"  # version spec
    r"\s*(?:;.*)?$"                                     # optional env marker
)

# TOML key = value assignments — NOT package requirements
_TOML_KV_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*\s*=\s*[^=<>!~]')

# Minimum set of known non-package identifiers (TOML keys, Python keywords, etc.)
_NON_PKG_IDENTIFIERS = {
    "name", "description", "version", "readme", "license", "authors", "keywords",
    "classifiers", "requires_python", "build_backend", "build_system", "dynamic",
    "dependencies", "optional_dependencies", "project", "tool", "scripts",
    "urls", "homepage", "repository", "documentation", "changelog",
    # pytest / coverage config keys
    "testpaths", "asyncio_mode", "addopts", "pythonpath", "filterwarnings",
    "fail_under", "show_missing", "precision", "omit", "source",
    # ruff / black / isort config keys
    "line_length", "target_version", "select", "ignore", "exclude",
    "per_file_ignores", "quote_style", "profile", "indent_width",
    # semantic-release / commitizen config keys
    "parse_squash_commits", "ignore_merge_commits", "minor_tags", "patch_tags",
    # uv.lock / poetry.lock structural keys
    "wheels", "sdist", "source", "content_hash", "metadata",
    # Python keywords that can appear in source-file diffs
    "if", "else", "for", "while", "return", "import", "from", "class", "def",
    "try", "except", "with", "pass", "break", "continue", "yield", "raise",
    "not", "and", "or", "in", "is", "as", "lambda", "global", "nonlocal",
    # setup.cfg [metadata] keys
    "long_description", "long_description_content_type", "license_file",
    "author", "author_email", "maintainer", "maintainer_email",
    "programming", "development", "intended", "topic", "operating", "natural",
    # misc structural tokens
    "include_package_data", "test_suite", "tests_require", "python_requires",
    "console_scripts", "entry_points", "packages", "package_dir", "package_data",
}


def parse_patch(patch: str, filepath: str = "") -> list[dict]:
    """+/- diff 라인에서 pip-installable dep change 추출.

    파일 유형에 따라 파싱 전략을 분기:
      - requirements*.txt / constraints*.txt : 모든 비주석 라인
      - pyproject.toml / setup.cfg / setup.py / Pipfile : 따옴표로 감싼 dep 항목만

    TOML key=value 할당, 설정 파일 키, Python 키워드 등은 제외한다.

    Returns:
        [{package, original_line, new_line, specifier, change_type}]
    """
    is_req_file = bool(re.search(
        r'requirements[^/]*\.txt$|requirements[^/]*\.in$|constraints[^/]*\.txt$',
        filepath, re.I
    ))
    is_lock_file = bool(re.search(r'\.(lock|lockfile)$', filepath, re.I))

    added = {}
    removed = {}

    for raw_line in patch.split("\n"):
        if raw_line.startswith(("+++", "---", "@@", "\\ ")):
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+#"):
            sign = "added"
            content = raw_line[1:].strip()
        elif raw_line.startswith("-") and not raw_line.startswith("-#"):
            sign = "removed"
            content = raw_line[1:].strip()
        else:
            continue

        if not content or content.startswith("#"):
            continue

        # Lock files: skip entirely (not direct deps)
        if is_lock_file:
            continue

        # TOML key = value assignment (name = "...", testpaths = [...], etc.)
        if _TOML_KV_RE.match(content):
            continue

        # Non-requirements files: only accept quoted package strings
        # e.g., `    "requests>=2.28",` inside TOML dep arrays
        if not is_req_file:
            if content.startswith(('"', "'")):
                # strip quotes + trailing comma
                content = content.rstrip(',').strip().strip('"\'').strip()
                # Skip entry-point paths like "module.submodule:function"
                if ':' in content:
                    continue
                # Unversioned bare names in non-req files are ambiguous (could be
                # coverage source, tool config, or local module). Require a version
                # spec to distinguish genuine PyPI deps from config values.
                # Exception: dot-separated names (namespace pkgs) are skipped.
                has_version_spec = bool(re.search(r'[><=!~^]', content))
                if not has_version_spec:
                    continue
            else:
                # Bare identifier in non-req file — skip unless it has a version spec
                # (avoids optional-dep group names like `dev`, `api`, entry points, etc.)
                has_version_spec = bool(re.search(r'[><=!~^]', content))
                if not has_version_spec:
                    continue

        # Final regex match against known package-name pattern
        m = _PKG_RE.match(content)
        if not m:
            continue
        pkg_name = m.group(1).lower().replace("-", "_")

        # Skip known non-package identifiers
        if pkg_name in _NON_PKG_IDENTIFIERS:
            continue

        # Skip if name looks like a Python keyword or too short to be a package
        if len(pkg_name) <= 1:
            continue

        target = added if sign == "added" else removed
        target[pkg_name] = content

    changes = []
    for name, line in added.items():
        ct = "modified" if name in removed else "added"
        changes.append({
            "package": name,
            "original_line": removed.get(name),
            "new_line": line,
            "specifier": None,
            "change_type": ct,
        })
    for name, line in removed.items():
        if name not in added:
            changes.append({
                "package": name,
                "original_line": line,
                "new_line": None,
                "specifier": None,
                "change_type": "removed",
            })
    return changes


def evaluate(prs: list[dict]) -> dict:
    """모든 PR 에 Guard B3 적용."""
    # Deduplicate by PR URL — the scale-up input list contained exact-duplicate
    # PR records, which would otherwise double-count distinct PRs.
    _seen_urls = set()
    _deduped = []
    for pr in prs:
        u = pr.get("html_url")
        if u in _seen_urls:
            continue
        _seen_urls.add(u)
        _deduped.append(pr)
    if len(_deduped) != len(prs):
        print(f"  deduped PRs by url: {len(prs)} -> {len(_deduped)}")
    prs = _deduped

    per_pr = []
    risk_label_counts = {}
    by_agent = {}
    by_stage = {}
    n_with_risk = 0

    # Empty evidence_refs → exploratory S1 snapshot-missing warnings,
    # S3/S4/S5/S6 는 evidence 없으면 skip
    empty_evidence = {"pypi_packages": {}, "vulnerability_advisories": [], "license_metadata": {}, "dependency_graphs": {}, "runtime_compatibility": []}
    # 기본 policy (모든 PR 에 공통 적용 — task-specific policy 없으므로)
    default_policy = {
        "allowed_licenses": ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "PSF-2.0"],
        "blocked_licenses": ["GPL-2.0", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0", "GPL-3.0-only", "GPL-3.0-or-later", "AGPL-3.0-only", "AGPL-3.0-or-later"],
        "unknown_license_policy": "warn",
        "vulnerability_policy": {"min_blocked_severity": "HIGH"},
        "dependency_free_expected": False,
    }

    for pr in prs:
        # PR 의 모든 manifest patch 통합
        all_changes = []
        for m in pr.get("dep_changes", []):
            all_changes.extend(parse_patch(m.get("patch", ""), m.get("path", "")))
        # dedup by package
        seen = {}
        for c in all_changes:
            if c["package"] not in seen:
                seen[c["package"]] = c
        deps = list(seen.values())

        if not deps:
            per_pr.append({
                "url": pr["html_url"], "agent": pr["agent"],
                "n_deps": 0, "guard_decision": "PASS", "risks": []
            })
            continue

        # Guard B3 (full)
        g = run_guard(
            deps,
            empty_evidence,
            default_policy,
            mode="B3",
            missing_evidence="warn_unknown",
        )
        risks = g.get("risk_report", []) or []
        per_pr.append({
            "url": pr["html_url"],
            "agent": pr["agent"],
            "n_deps": len(deps),
            "deps_sample": [d["package"] for d in deps[:5]],
            "guard_decision": g["decision"],
            "risks": [{"stage": r.get("stage"), "label": r.get("risk_label"), "pkg": r.get("package"), "reason": r.get("reason", "")[:120]} for r in risks],
        })
        if risks:
            n_with_risk += 1
        for r in risks:
            label = r.get("risk_label", "unknown")
            stage = r.get("stage", "?")
            risk_label_counts[label] = risk_label_counts.get(label, 0) + 1
            by_stage[stage] = by_stage.get(stage, 0) + 1
        by_agent.setdefault(pr["agent"], {"total": 0, "with_risk": 0})
        by_agent[pr["agent"]]["total"] += 1
        if risks:
            by_agent[pr["agent"]]["with_risk"] += 1

    return {
        "n_prs": len(prs),
        "n_with_risk": n_with_risk,
        "risk_label_counts": risk_label_counts,
        "by_stage": by_stage,
        "by_agent": by_agent,
        "per_pr": per_pr,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=Path("results/aidev_sample.jsonl"))
    p.add_argument("--output", type=Path, default=Path("results/aidev_evaluation.json"))
    args = p.parse_args()

    prs = [json.loads(l) for l in args.input.read_text().splitlines() if l.strip()]
    print(f"Loaded {len(prs)} PRs")

    summary = evaluate(prs)
    args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\n=== Summary ===")
    print(f"n_prs: {summary['n_prs']}")
    print(f"n_with_risk: {summary['n_with_risk']} ({100*summary['n_with_risk']/summary['n_prs']:.1f}%)")
    print(f"risk_label_counts: {summary['risk_label_counts']}")
    print(f"by_stage: {summary['by_stage']}")
    print(f"by_agent: {summary['by_agent']}")
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()

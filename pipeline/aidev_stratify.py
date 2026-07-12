"""
Artifact D: AIDev PR stratification.

Classify all 61 PRs into:
  existing_dep_update    -- existing package version bumped
  new_runtime_dep        -- agent adds a new package to runtime dependencies
  new_devtest_dep        -- agent adds to dev/test optional-deps group only
  optional_dep_addition  -- agent adds to [project.optional-dependencies] non-dev group
  metadata_config_only   -- only metadata or config keys changed (no real dep)
  mixed                  -- combination of above

For each PR, parse the actual dep_changes patches to determine what changed.

Output:
  results/aidev_stratification.csv
  results/aidev_stratification_summary.md
"""

import csv
import json
import re
from pathlib import Path
from collections import Counter

SAMPLE_FILE = Path("results/aidev_sample_v2.jsonl")
EVAL_FILE   = Path("results/aidev_evaluation_v4.json")
OUT_CSV     = Path("results/aidev_stratification.csv")
OUT_MD      = Path("results/aidev_stratification_summary.md")

# Patterns that identify non-package lines
METADATA_KEYS = {
    "name", "description", "version", "readme", "license", "authors",
    "keywords", "classifiers", "requires_python", "build_backend",
    "dynamic", "urls", "homepage", "repository", "documentation",
    "testpaths", "asyncio_mode", "addopts", "pythonpath", "filterwarnings",
    "fail_under", "show_missing", "precision", "omit", "source",
    "line_length", "target_version", "select", "ignore", "exclude",
    "per_file_ignores", "quote_style", "profile", "indent_width",
    "parse_squash_commits", "ignore_merge_commits", "minor_tags", "patch_tags",
    "wheels", "sdist", "content_hash", "metadata",
    "if", "else", "for", "while", "return", "import", "from", "class",
    "def", "try", "except", "with", "pass", "break", "continue",
    "long_description", "long_description_content_type", "license_file",
    "include_package_data", "test_suite", "tests_require", "python_requires",
    "console_scripts", "entry_points", "packages", "package_dir",
}

DEV_GROUP_NAMES = {"dev", "test", "tests", "testing", "lint", "check", "ci", "docs", "build"}
OPT_GROUP_NAMES = {"api", "bulk_api", "video", "eeg_sync", "agent", "scripts", "extras"}

# Real package name regex (bare, no TOML KV)
PKG_RE = re.compile(r'^([A-Za-z0-9][A-Za-z0-9._-]*(?:\[[^\]]+\])?)\s*([><=!~^].+)?$')
TOML_KV = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*\s*=\s*[^=<>!~]')


def classify_patch_line(line: str, in_dev_group: bool, in_opt_group: bool) -> str:
    """Return one of: real_runtime, real_dev, real_optional, not_package, version_update"""
    content = line.strip()
    if not content or content.startswith("#"):
        return "skip"
    if TOML_KV.match(content):
        return "not_package"
    # Quoted TOML dep entry
    if content.startswith('"') or content.startswith("'"):
        content = content.strip('"\'').rstrip(",").strip()
    m = PKG_RE.match(content)
    if not m:
        return "not_package"
    pkg = m.group(1).lower().replace("-","_")
    if pkg in METADATA_KEYS:
        return "not_package"
    if len(pkg) <= 1:
        return "not_package"
    if in_dev_group:
        return "real_dev"
    if in_opt_group:
        return "real_optional"
    return "real_runtime"


def analyze_pr_patches(dep_changes: list[dict]) -> dict:
    """Analyze what type of change each PR makes."""
    has_runtime_add   = False
    has_runtime_mod   = False
    has_dev_add       = False
    has_optional_add  = False
    has_metadata_only = False
    has_real_change   = False

    for manifest in dep_changes:
        path  = manifest.get("path","")
        patch = manifest.get("patch","")
        is_req_file = bool(re.search(r'requirements[^/]*\.txt$|constraints[^/]*\.txt$', path, re.I))

        in_dev_section  = False
        in_opt_section  = False
        in_dep_section  = False
        current_group   = None

        for raw_line in patch.split("\n"):
            # Track TOML sections
            section_m = re.match(r'^\s*\[([^\]]+)\]', raw_line.lstrip("+-"))
            if section_m:
                sec = section_m.group(1).lower()
                if "optional-dependencies" in sec or "optional_dependencies" in sec:
                    group_m = re.search(r'\.\s*(\w+)\s*$', sec)
                    if group_m:
                        current_group = group_m.group(1).lower()
                        in_dev_section = current_group in DEV_GROUP_NAMES
                        in_opt_section = current_group in OPT_GROUP_NAMES and not in_dev_section
                    else:
                        in_dev_section = False
                        in_opt_section = True
                elif "dependencies" in sec and "optional" not in sec and "build" not in sec:
                    in_dep_section = True
                    in_dev_section = False
                    in_opt_section = False
                    current_group = None
                elif "tool." in sec or "build" in sec or "project.urls" in sec or "metadata" in sec:
                    in_dep_section = False
                    in_dev_section = False
                    in_opt_section = False
                continue

            if not (raw_line.startswith("+") or raw_line.startswith("-")):
                continue
            is_add = raw_line.startswith("+")
            if raw_line.startswith(("+++","---")):
                continue
            content = raw_line[1:].strip()

            if is_req_file:
                cat = classify_patch_line(content, False, False)
            else:
                cat = classify_patch_line(content, in_dev_section, in_opt_section)

            if cat == "not_package":
                has_metadata_only = True
            elif cat == "real_runtime" and is_add:
                has_runtime_add  = True
                has_real_change  = True
            elif cat == "real_runtime" and not is_add:
                has_runtime_mod  = True
                has_real_change  = True
            elif cat == "real_dev" and is_add:
                has_dev_add      = True
                has_real_change  = True
            elif cat == "real_optional" and is_add:
                has_optional_add = True
                has_real_change  = True

    # Classify PR
    if not has_real_change:
        category = "metadata_config_only"
    elif has_runtime_add and not has_runtime_mod and not has_dev_add:
        category = "new_runtime_dep"
    elif has_runtime_mod and not has_runtime_add and not has_dev_add:
        category = "existing_dep_update"
    elif has_dev_add and not has_runtime_add:
        category = "new_devtest_dep"
    elif has_optional_add and not has_runtime_add:
        category = "optional_dep_addition"
    else:
        category = "mixed"

    return {
        "category": category,
        "has_runtime_add": has_runtime_add,
        "has_runtime_mod": has_runtime_mod,
        "has_dev_add": has_dev_add,
        "has_optional_add": has_optional_add,
        "has_metadata_only": has_metadata_only,
    }


def _guard_category(pr_eval: dict) -> str:
    """Map a per_pr eval record to primary / gap_only / true_neg, handling both
    the v4 schema (primary_risks/evidence_gap_risks) and the scale-up schema
    (a single `risks` list of {stage,label})."""
    if pr_eval.get("primary_risks"):
        return "primary"
    if pr_eval.get("evidence_gap_risks"):
        return "gap_only"
    risks = pr_eval.get("risks") or []
    stages = {r.get("stage") for r in risks}
    if stages & {"S1", "S3"}:
        return "primary"
    if risks:
        return "gap_only"
    return "true_neg"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample",  type=Path, default=SAMPLE_FILE)
    ap.add_argument("--eval",    type=Path, default=EVAL_FILE)
    ap.add_argument("--out-csv", type=Path, default=OUT_CSV)
    ap.add_argument("--out-md",  type=Path, default=OUT_MD)
    args = ap.parse_args()

    eval_data = json.loads(args.eval.read_text())
    per_pr_eval = {pr["url"]: pr for pr in eval_data.get("per_pr", [])}

    sample_map = {}
    n_bad = 0
    with args.sample.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                n_bad += 1
                continue
            sample_map[r["html_url"]] = r
    if n_bad:
        print(f"  warning: skipped {n_bad} malformed sample line(s)")

    rows = []
    for pr_eval in eval_data.get("per_pr", []):
        url   = pr_eval["url"]
        agent = pr_eval["agent"]
        meta  = sample_map.get(url, {})
        dep_changes = []
        raw_dc = meta.get("dep_changes", "")
        if isinstance(raw_dc, list):
            dep_changes = raw_dc
        elif isinstance(raw_dc, str):
            try:
                dep_changes = eval(raw_dc) if raw_dc.startswith("[") else []
            except Exception:
                dep_changes = []

        analysis = analyze_pr_patches(dep_changes)
        guard_cat = _guard_category(pr_eval)

        rows.append({
            "url": url,
            "agent": agent,
            "created_at": meta.get("created_at","")[:10],
            "n_deps": pr_eval.get("n_deps", 0),
            "guard_category": guard_cat,
            **analysis,
        })

    with args.out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {args.out_csv}")

    cats = Counter(r["category"] for r in rows)
    n_new_runtime = sum(1 for r in rows if r["category"] == "new_runtime_dep")
    n_mixed_runtime = sum(1 for r in rows if r["category"] == "mixed" and r["has_runtime_add"])
    n_agent_chosen_new = n_new_runtime + n_mixed_runtime

    # cross-tab with guard outcome
    from collections import defaultdict
    cross = defaultdict(Counter)
    for r in rows:
        cross[r["category"]][r["guard_category"]] += 1

    md_lines = [
        "# Artifact D: AIDev PR Stratification\n",
        f"Total PRs: {len(rows)}\n",
        "## PR category distribution\n",
        "| Category | Count | Description |",
        "|----------|-------|-------------|",
    ]
    cat_desc = {
        "new_runtime_dep":     "Agent adds new package to runtime dependencies",
        "existing_dep_update": "Existing package version bumped only",
        "new_devtest_dep":     "New package added to dev/test optional-deps only",
        "optional_dep_addition":"New package in non-dev optional-deps group",
        "metadata_config_only": "Only metadata/config keys changed, no real dep",
        "mixed":               "Combination of above",
    }
    for cat in ["new_runtime_dep","existing_dep_update","new_devtest_dep",
                "optional_dep_addition","metadata_config_only","mixed"]:
        md_lines.append(f"| {cat} | {cats[cat]} | {cat_desc.get(cat,'')} |")

    md_lines += [
        f"\n**PRs with agent-chosen new runtime dependencies: {n_agent_chosen_new}**",
        f"(new_runtime_dep={n_new_runtime} + mixed with runtime_add={n_mixed_runtime})\n",
        "## Guard outcome × PR category\n",
        "| Category | primary | gap_only | true_neg |",
        "|----------|---------|----------|----------|",
    ]
    for cat in ["new_runtime_dep","existing_dep_update","new_devtest_dep",
                "optional_dep_addition","metadata_config_only","mixed"]:
        c = cross[cat]
        md_lines.append(f"| {cat} | {c['primary']} | {c['gap_only']} | {c['true_neg']} |")

    md_lines += [
        "\n## Implication for external validation claim\n",
        f"Only {n_agent_chosen_new}/{len(rows)} PRs involve agent-chosen new runtime dependencies.",
        "The remaining PRs are version updates, dev-dep additions, metadata changes, or mixed.",
        "The zero primary-risk finding is therefore specific to this distribution of PR types.",
        "A sample targeting agent-chosen new runtime dependencies would be needed to",
        "test whether the risk families from the controlled benchmark appear in production.",
    ]

    args.out_md.write_text("\n".join(md_lines))
    print(f"Wrote {args.out_md}")
    print("\nCategory breakdown:", dict(cats))
    print(f"Agent-chosen new runtime deps: {n_agent_chosen_new}/{len(rows)}")


if __name__ == "__main__":
    main()

from collections import defaultdict

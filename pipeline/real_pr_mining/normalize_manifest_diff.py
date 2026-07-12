"""Manifest-type detection, PEP 503 normalization, specifier parsing, and
runtime/optional/dev section classification for real-PR dependency diffs.

Extraction of *which* tokens are packages is delegated to the existing,
well-tested ``pipeline.aidev_evaluate.parse_patch``. This module only adds the
metadata the real-PR corpus needs on top of that authoritative package set.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.aidev_evaluate import parse_patch  # noqa: E402

# Dev/test/tooling optional-dependency group names.
DEV_GROUP_NAMES = {
    "dev", "develop", "development", "test", "tests", "testing", "lint",
    "linting", "docs", "doc", "typing", "mypy", "ci", "build", "check", "style",
}


def detect_manifest_type(path: str):
    """Map a repo-relative path to one of the 9 manifest_type enum values, or None.

    requirements*.txt / *.in / constraints*.txt under a ``requirements/`` dir are
    classified as ``requirements_dir``; elsewhere as ``requirements_txt``.
    """
    if not path:
        return None
    p = path.strip().replace("\\", "/")
    base = p.rsplit("/", 1)[-1].lower()

    if re.search(r"(^|/)requirements/.+\.(txt|in)$", p, re.I):
        return "requirements_dir"
    if re.match(r"(requirements.*|constraints.*)\.(txt|in)$", base):
        return "requirements_txt"
    if base == "pyproject.toml":
        return "pyproject_toml"
    if base == "setup.py":
        return "setup_py"
    if base == "setup.cfg":
        return "setup_cfg"
    if base == "pipfile":
        return "pipfile"
    if base == "poetry.lock":
        return "poetry_lock"
    if base == "uv.lock":
        return "uv_lock"
    if base == "pdm.lock":
        return "pdm_lock"
    return None


def normalize_name(name: str) -> str:
    """PEP 503 normalized name: lowercase, runs of [-_.] collapsed to a single '-'."""
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


_NAME_PREFIX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


def _strip_to_requirement(line: str) -> str:
    """Strip quotes/comma/inline-comment/env-marker noise to a bare requirement."""
    s = line.strip()
    if s[:1] in ("'", '"'):
        s = s.rstrip(",").strip().strip("'\"").strip()
    s = re.split(r"\s+#", s, maxsplit=1)[0].strip()  # inline comment
    s = s.split(";", 1)[0].strip()                    # env marker
    return s


def parse_specifier(line):
    """Return the raw version-specifier clause (e.g. '>=2.0,<3'), or None."""
    s = _strip_to_requirement(line)
    m = _NAME_PREFIX.match(s)
    if not m:
        return None
    rest = s[m.end():]
    rest = re.sub(r"^\s*\[[^\]]*\]", "", rest).strip()  # drop extras
    rest = rest.replace(" ", "")
    return rest or None


def extract_version_pin(line):
    """Return the exact version if the specifier is a single '==' pin, else None."""
    spec = parse_specifier(line)
    if not spec:
        return None
    if spec.startswith("==") and "," not in spec:
        ver = spec[2:]
        # `==X.*` is a PEP 440 prefix match, not a concrete pinned version.
        if "*" in ver:
            return None
        return ver or None
    return None


def _pkg_key(line: str):
    """parse_patch's normalization key (lower, '-'->'_') for a requirement line."""
    s = _strip_to_requirement(line)
    m = _NAME_PREFIX.match(s)
    if not m:
        return None
    return m.group(0).lower().replace("-", "_")


def _is_dev_requirements(path: str) -> bool:
    p = path.lower()
    base = p.rsplit("/", 1)[-1]
    if re.search(r"(^|[-_/])(dev|test|tests|lint|docs|typing|ci)([-_.]|$)", base):
        return True
    if re.search(r"requirements/(dev|test|tests|lint|docs|typing|ci)", p):
        return True
    return False


def _kind_for(table, group):
    """Classify (is_runtime, is_optional, is_dev) from TOML table + array context."""
    t = (table or "").lower()
    g = (group or "").lower()
    is_optional = "optional-dependencies" in t
    is_dev = False
    is_runtime = False
    if is_optional:
        is_dev = g in DEV_GROUP_NAMES
    elif t == "dependency-groups":
        is_optional = False
        is_dev = True  # PEP 735 dependency groups are non-runtime
    elif t.endswith("dev-dependencies") or re.search(r"\.group\.[^.]+\.dependencies$", t):
        is_dev = bool(re.search(r"\.group\.(dev|test|tests|lint|docs|typing|ci)\.", t)) \
            or t.endswith("dev-dependencies")
        is_optional = not is_dev
    else:
        # [project] dependencies / [tool.poetry.dependencies] / plain
        is_runtime = True
    if not (is_optional or is_dev or is_runtime):
        is_runtime = True
    return {"is_runtime": is_runtime, "is_optional": is_optional, "is_dev": is_dev}


def section_kinds(patch: str, filepath: str) -> dict:
    """Map each parse_patch package key in `patch` to its runtime/optional/dev kind."""
    mtype = detect_manifest_type(filepath)
    keys = {c["package"] for c in parse_patch(patch, filepath)}
    result = {}

    if mtype in ("requirements_txt", "requirements_dir"):
        dev = _is_dev_requirements(filepath)
        for k in keys:
            result[k] = {"is_runtime": not dev, "is_optional": False, "is_dev": dev}
        return result

    if mtype == "pyproject_toml":
        cur_table = None
        cur_group = None
        for raw in patch.split("\n"):
            if raw.startswith(("+++", "---", "@@", "\\ ")):
                continue
            line = raw[1:] if raw[:1] in "+- " else raw
            s = line.strip()
            mh = re.match(r"\[([^\]]+)\]", s)
            if mh:
                cur_table = mh.group(1).strip()
                cur_group = None
                continue
            ma = re.match(r'["\']?([A-Za-z0-9._-]+)["\']?\s*=\s*\[', s)
            if ma:
                cur_group = ma.group(1).strip()
                continue
            key = _pkg_key(s)
            if key and key in keys:
                result[key] = _kind_for(cur_table, cur_group)
        for k in keys:
            result.setdefault(k, {"is_runtime": True, "is_optional": False, "is_dev": False})
        return result

    # setup.py / setup.cfg / Pipfile: section context is unreliable -> runtime, rest unknown
    for k in keys:
        result[k] = {"is_runtime": True, "is_optional": None, "is_dev": None}
    return result

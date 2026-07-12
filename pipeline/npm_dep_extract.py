#!/usr/bin/env python3
"""Structural package.json dependency extraction + diff (PyPI dep_extractor analogue).

Mirrors pipeline/dep_extractor.py exactly in spirit: parse the ACTUAL manifest
JSON (not raw diff lines) so non-dependency keys -- a root "version"/"name"/
"description", a "scripts" entry -- can never be mistaken for a dependency, and
non-registry specs (workspace:/file:/link:/portal:/git/url/npm: alias/github
shorthand) are dropped exactly as the PyPI extractor drops VCS/editable/URL
requirement lines (anything with "://" or starting with "-").

Risk domain = the add + version_change changes; removals are excluded from
prevalence (removing a dependency cannot introduce a non-existent package, an
invalid version, or an advisory-bearing pin -- same rule as the PyPI study).
"""
from __future__ import annotations

import json
import re

DEP_BLOCKS = ("dependencies", "devDependencies",
              "peerDependencies", "optionalDependencies")

# npm spec protocols that do NOT resolve from the public registry -> not
# evaluable for F1/F2/F3. Direct analogue of the PyPI extractor dropping
# git+/-e/file://// "://" requirement lines.
_PROTOCOL_RE = re.compile(
    r"^(workspace:|file:|link:|portal:|git[:+]|git@|github:|gitlab:|bitbucket:|"
    r"https?://|npm:|catalog:|patch:|jsr:)", re.I)


def is_registry_spec(spec: str) -> bool:
    """True iff `spec` is a public-registry version spec (semver range / wildcard /
    bare-latest) that npm would resolve from registry.npmjs.org. False for
    protocol / VCS / url / alias / local-path / github-shorthand specs."""
    s = (spec or "").strip()
    if s == "":
        return False
    if _PROTOCOL_RE.match(s):
        return False
    head = s.split("#", 1)[0]
    # github shorthand (owner/repo[#ref]) or local path (./x, ../x) -> has a slash;
    # a registry semver spec never contains '/'. (Scoped names are KEYS, not specs.)
    if "/" in head:
        return False
    if head.endswith(".git"):
        return False
    return True


def parse_pkg_json(text: str) -> dict:
    """Tolerant package.json parse -> {block: {name: spec}} over the 4 dep blocks.
    Returns {} when unparseable. Tolerates BOM, // and /* */ comments, and
    trailing commas (some agent-written package.json drift toward JSON5)."""
    if not text:
        return {}
    t = text.lstrip("﻿")
    doc = None
    try:
        doc = json.loads(t)
    except Exception:
        t2 = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        t2 = re.sub(r"(^|[^:])//[^\n]*", lambda m: m.group(1), t2)
        t2 = re.sub(r",(\s*[}\]])", r"\1", t2)
        try:
            doc = json.loads(t2)
        except Exception:
            return {}
    if not isinstance(doc, dict):
        return {}
    out: dict = {}
    for b in DEP_BLOCKS:
        v = doc.get(b)
        if isinstance(v, dict):
            out[b] = {str(k): str(val) for k, val in v.items()
                      if isinstance(val, str)}
    return out


def flatten(blocks: dict) -> dict:
    """{block:{name:spec}} -> {name: (block, spec)} (first dep block wins on dup)."""
    flat: dict = {}
    for b in DEP_BLOCKS:
        for name, spec in blocks.get(b, {}).items():
            flat.setdefault(name, (b, spec))
    return flat


def diff_changes(old_text: str, new_text: str) -> list[dict]:
    """Risky changes between two package.json texts: [{name, block, spec,
    change_type}] for change_type in {add, version_change}. Removals dropped
    (excluded from prevalence). Non-registry specs dropped (not evaluable),
    mirroring the PyPI extractor."""
    old = flatten(parse_pkg_json(old_text))
    new = flatten(parse_pkg_json(new_text))
    changes = []
    for name, (block, spec) in new.items():
        if name not in old:
            ct = "add"
        elif old[name][1].strip() != spec.strip():
            ct = "version_change"
        else:
            continue
        if not is_registry_spec(spec):
            continue
        changes.append({"name": name, "block": block,
                        "spec": spec, "change_type": ct})
    return changes


# exact-pin detection for F2 (PyPI F2 = an exact pin whose version is absent/yanked)
_EXACT_RE = re.compile(r"^[v=]?\s*\d+\.\d+\.\d+([-+][0-9A-Za-z.\-]+)?$")


def is_exact_pin(spec: str) -> str | None:
    """Return the pinned version string if `spec` is an exact pin (1.2.3 / =1.2.3 /
    v1.2.3), else None. Used so F2 fires only on exact pins, like the PyPI study."""
    s = (spec or "").strip()
    if not _EXACT_RE.match(s):
        return None
    return s.lstrip("v=").strip()

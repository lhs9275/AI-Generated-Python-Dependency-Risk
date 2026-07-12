"""License metadata snapshot, derived from PyPI JSON, with explicit
license_missing handling. Reported as evidence-gap noise, kept separate from the
S1/S3 primary signals (see docs/protocols/claim_freeze.md W3)."""

import re

_UNKNOWN = {"", "unknown", "none", "n/a", "uncategorized"}
# Minimal SPDX-ish normalization for common classifier strings.
_CLASSIFIER_SPDX = [
    (r"Apache Software License", "Apache-2.0"),
    (r"MIT License", "MIT"),
    (r"BSD License", "BSD-3-Clause"),
    (r"GNU Lesser General Public License v3", "LGPL-3.0"),
    (r"GNU Lesser General Public License", "LGPL-2.1"),
    (r"GNU General Public License v3", "GPL-3.0"),
    (r"GNU General Public License", "GPL-2.0"),
    (r"Mozilla Public License 2.0", "MPL-2.0"),
    (r"ISC License", "ISC"),
    (r"The Unlicense", "Unlicense"),
]


def license_from_pypi(j: dict):
    """Return (license_spdx_or_raw, license_missing: bool) for the package."""
    info = (j or {}).get("info", {}) or {}
    raw = (info.get("license") or "").strip()
    if raw and raw.lower() not in _UNKNOWN and len(raw) < 100:
        return raw, False

    classifiers = info.get("classifiers", []) or []
    lic_classifiers = [c for c in classifiers if c.startswith("License ::")]
    if lic_classifiers:
        text = " ".join(lic_classifiers)
        for pat, spdx in _CLASSIFIER_SPDX:
            if re.search(pat, text):
                return spdx, False
        # A license classifier exists but is unrecognized: not missing, just unmapped.
        return lic_classifiers[-1].split("::")[-1].strip(), False

    # PEP 639 license expression field (newer metadata).
    expr = (info.get("license_expression") or "").strip()
    if expr and expr.lower() not in _UNKNOWN:
        return expr, False

    return None, True

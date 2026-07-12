#!/usr/bin/env python3
"""Minimal, dependency-free npm semver range matcher.

Just enough of node-semver to resolve the dependency specs that appear in real
package.json diffs (caret/tilde/exact/x-range/partial/comparator-set/hyphen/||)
against a package's published version list, for automated F2 (invalid/yanked
version) and F3 (version-aware OSV) labeling. Pure release-tuple comparison;
prerelease versions are excluded from a stable range (npm semantics) and exotic
specs we cannot parse return None so the caller can mark them non-evaluable
rather than guess. No third-party packages -> reproducible offline.
"""
from __future__ import annotations

import re

_REL = re.compile(r"^[v=]*\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_INF = (1 << 30, 0, 0)


def parse_version(v: str):
    """'1.2.3' / 'v1.2.3' -> (1,2,3); None if not a concrete release."""
    s = (v or "").strip()
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", s)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def is_prerelease(v: str) -> bool:
    core = (v or "").split("+", 1)[0]
    return "-" in core


def _xparse(token: str):
    """Parse a possibly-partial / x-range version token to (maj,min,pat) ints
    with None for wildcard positions. '1.2.x'->(1,2,None); '1'->(1,None,None);
    '*'/''->(None,None,None). Returns None if not a version token."""
    t = token.strip().lstrip("v=")
    if t in ("", "*", "x", "X"):
        return (None, None, None)
    parts = t.split(".")
    out = []
    for p in parts[:3]:
        if p in ("x", "X", "*"):
            out.append(None)
        elif p.isdigit():
            out.append(int(p))
        else:
            return None
    while len(out) < 3:
        out.append(None)
    return tuple(out)


def _bounds_from_xrange(xr):
    """(maj,min,pat with None wildcards) -> (lo_incl, hi_excl) tuples."""
    maj, mn, pt = xr
    if maj is None:
        return (0, 0, 0), _INF
    if mn is None:
        return (maj, 0, 0), (maj + 1, 0, 0)
    if pt is None:
        return (maj, mn, 0), (maj, mn + 1, 0)
    return (maj, mn, pt), None  # fully specified -> exact handled by caller


def _caret(xr):
    maj, mn, pt = (xr[0] or 0, xr[1] or 0, xr[2] or 0)
    lo = (maj, mn, pt)
    if xr[0] and maj > 0:
        hi = (maj + 1, 0, 0)
    elif (xr[1] is not None) and mn > 0:
        hi = (maj, mn + 1, 0)
    elif xr[2] is not None:
        hi = (maj, mn, pt + 1)
    else:  # ^0 or ^0.0
        hi = (maj, (mn + 1) if xr[1] is not None else 1, 0) if mn == 0 else (maj, mn + 1, 0)
        if xr[1] is None:
            hi = (1, 0, 0)
    return lo, hi


def _tilde(xr):
    maj, mn, pt = (xr[0] or 0, xr[1] or 0, xr[2] or 0)
    lo = (maj, mn, pt)
    if xr[1] is not None:        # ~1.2 or ~1.2.3 -> <1.3.0
        hi = (maj, mn + 1, 0)
    else:                        # ~1 -> <2.0.0
        hi = (maj + 1, 0, 0)
    return lo, hi


class _Interval:
    """Half-open-ish interval with inclusive/exclusive flags. None bound = open."""
    __slots__ = ("lo", "lo_incl", "hi", "hi_incl")

    def __init__(self, lo=None, lo_incl=True, hi=None, hi_incl=False):
        self.lo, self.lo_incl, self.hi, self.hi_incl = lo, lo_incl, hi, hi_incl

    def contains(self, t):
        if self.lo is not None:
            if t < self.lo or (t == self.lo and not self.lo_incl):
                return False
        if self.hi is not None:
            if t > self.hi or (t == self.hi and not self.hi_incl):
                return False
        return True

    def intersect(self, o):
        lo, lo_incl = self.lo, self.lo_incl
        if o.lo is not None and (lo is None or o.lo > lo or (o.lo == lo and not o.lo_incl)):
            lo, lo_incl = o.lo, o.lo_incl
        hi, hi_incl = self.hi, self.hi_incl
        if o.hi is not None and (hi is None or o.hi < hi or (o.hi == hi and not o.hi_incl)):
            hi, hi_incl = o.hi, o.hi_incl
        return _Interval(lo, lo_incl, hi, hi_incl)


def _comparator(tok):
    """One comparator -> _Interval, or None if unparseable."""
    tok = tok.strip()
    if tok == "":
        return _Interval()  # matches all
    if tok[0] == "^":
        xr = _xparse(tok[1:])
        if xr is None:
            return None
        lo, hi = _caret(xr)
        return _Interval(lo, True, hi, False)
    if tok[0] == "~":
        xr = _xparse(tok[1:])
        if xr is None:
            return None
        lo, hi = _tilde(xr)
        return _Interval(lo, True, hi, False)
    for op in (">=", "<=", ">", "<", "="):
        if tok.startswith(op):
            v = parse_version(tok[len(op):]) or _xparse(tok[len(op):])
            if v is None or (isinstance(v, tuple) and None in v and op in ("=",)):
                # partial with = -> treat as x-range below
                break
            if isinstance(v, tuple) and None in v:
                lo, hi = _bounds_from_xrange(v)
                if op == ">=":
                    return _Interval(lo, True, None, False)
                if op == ">":
                    return _Interval(hi, True, None, False) if hi else None
                if op == "<":
                    return _Interval(None, True, lo, False)
                if op == "<=":
                    return _Interval(None, True, hi, False) if hi else _Interval()
            if op == ">=":
                return _Interval(v, True, None, False)
            if op == ">":
                return _Interval(v, False, None, False)
            if op == "<=":
                return _Interval(None, True, v, True)
            if op == "<":
                return _Interval(None, True, v, False)
            if op == "=":
                return _Interval(v, True, v, True)
    # bare version / x-range / partial
    xr = _xparse(tok)
    if xr is None:
        return None
    if None not in xr:
        return _Interval(xr, True, xr, True)  # exact
    lo, hi = _bounds_from_xrange(xr)
    return _Interval(lo, True, hi, False) if hi else _Interval(lo, True, None, False)


def _comparator_set(part):
    """Space-separated comparators (AND), incl. hyphen range 'A - B'."""
    part = part.strip()
    if " - " in part:
        a, b = part.split(" - ", 1)
        lo = parse_version(a) or _bounds_from_xrange(_xparse(a) or (None, None, None))[0]
        bx = _xparse(b)
        if bx is None:
            return None
        if None in bx:
            hi = _bounds_from_xrange(bx)[1]
            return _Interval(lo, True, hi, False)
        return _Interval(lo, True, bx, True)
    iv = _Interval()
    for tok in part.split():
        c = _comparator(tok)
        if c is None:
            return None
        iv = iv.intersect(c)
    return iv


def matches(spec: str, version: str) -> bool | None:
    """Does `version` satisfy npm range `spec`? None if spec unparseable."""
    vt = parse_version(version)
    if vt is None:
        return None
    any_parsed = False
    for part in (spec or "").split("||"):
        iv = _comparator_set(part)
        if iv is None:
            continue
        any_parsed = True
        if iv.contains(vt):
            return True
    return False if any_parsed else None


UNPARSEABLE = "__UNPARSEABLE__"


def is_parseable(spec: str) -> bool:
    """True if at least one comparator of the spec parses (independent of any
    version list). Uses a dummy concrete version: matches() returns None only
    when the whole spec is unparseable."""
    return matches(spec, "0.0.0") is not None


def max_satisfying(spec: str, versions, include_prerelease: bool = False):
    """Highest published version satisfying spec (the one npm installs), or
    None if none satisfies (-> F2 risk); UNPARSEABLE if the spec itself cannot
    be parsed (caller marks non-evaluable, NOT a risk)."""
    if not is_parseable(spec):
        return UNPARSEABLE
    best = None
    for v in versions:
        if not include_prerelease and is_prerelease(v):
            continue
        if matches(spec, v) is True:
            vt = parse_version(v)
            if best is None or vt > parse_version(best):
                best = v
    return best

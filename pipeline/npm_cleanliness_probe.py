#!/usr/bin/env python3
"""npm_cleanliness_probe -- go/no-go quality gate before a full npm prevalence study.

The yield check (aidev_npm_yield.py) already proved the DATA IS ABUNDANT
(~25k-197k package.json-change agent PRs). It did NOT measure whether an npm
study would be *clean*. The real backfire risk flagged for the PyPI->npm port
is low dual-labeler agreement from npm semver-range ambiguity sitting next to
the clean PyPI kappa=0.90. This probe pulls a small REAL sample of
agent-authored package.json dependency changes and measures, with NO human
labeling, three machine-checkable signals that drive the risk families:

  (1) semver parseability  -- of the added/bumped dependency specs, how many
      resolve to a concrete version for an OSV/registry lookup (exact/caret/
      tilde/range) vs are non-resolvable (wildcard/latest/git/url/workspace/
      file/link). Drives F2 (invalid/yanked-version) detection feasibility.
  (2) registry existence   -- does the declared package name exist on the npm
      registry? (F1 hallucinated-name signal + evidence availability)
  (3) OSV-npm coverage     -- does OSV return advisories for the name?
      (F3 known-vuln evidence density vs the PyPI OSV adapter)

A clean GREEN looks like: most specs resolvable (low ambiguity -> F2 portable),
registry lookups deterministic (F1 portable), OSV returns hits at a rate
comparable to PyPI (F3 evidence density adequate). High wildcard/git-url share
or empty OSV coverage => npm labeling would be noisier than PyPI => the
backfire risk is real and the study should stay HOLD.

npm registry + OSV are unauthenticated; GitHub PR search/files need GITHUB_TOKEN
(classic public_repo or fine-grained public read-only). Token from $GITHUB_TOKEN
or ~/.gh_token, never on argv.

Output: results/npm_cleanliness_probe.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, os.path.dirname(__file__))
from aidev_collect import gh_request, get_pr_files, AGENT_QUERIES  # noqa: E402

NPM_REGISTRY = "https://registry.npmjs.org"
OSV_API = "https://api.osv.dev/v1/query"
NPM_MANIFEST = "package.json"
LANGS = ["JavaScript", "TypeScript"]

# package.json dependency blocks whose added lines declare a name->spec mapping.
DEP_BLOCKS = ("dependencies", "devDependencies", "peerDependencies",
              "optionalDependencies")
# An added JSON line like:  +    "lodash": "^4.17.21",
ADDED_DEP_RE = re.compile(r'^\+\s*"([^"]+)"\s*:\s*"([^"]*)"\s*,?\s*$')


def classify_spec(spec: str) -> str:
    """Bucket an npm version spec by how resolvable it is for an OSV/registry
    lookup. 'resolvable' buckets pin to a concrete version set; the rest cannot
    be checked against a registry/OSV the way a PyPI exact pin can."""
    s = (spec or "").strip()
    if s == "" or s in ("*", "x", "X", "latest", "next"):
        return "wildcard"          # non-resolvable
    low = s.lower()
    if (low.startswith(("git+", "git:", "http://", "https://", "file:",
                        "link:", "portal:", "workspace:", "npm:"))
            or low.startswith("github:") or "/" in s.split("#")[0] and ":" in low):
        return "non_registry"      # git/url/workspace/file/alias -> not a plain registry pin
    if s.startswith("^"):
        return "caret"
    if s.startswith("~"):
        return "tilde"
    if re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?", s):
        return "exact"
    if re.search(r"[<>=]| - | \|\| |\s", s) or "x" in low:
        return "range"
    if re.fullmatch(r"v?\d+(?:\.\d+)?", s):
        return "partial"           # e.g. "4" / "4.17" -> resolvable to a concrete set
    return "other"


RESOLVABLE = {"exact", "caret", "tilde", "range", "partial"}


def parse_added_deps(patch: str) -> list[tuple[str, str]]:
    """Extract (name, spec) pairs from + lines of a package.json diff that fall
    inside a dependency block. We track the most recent block header seen so a
    bare name->spec line is only counted when under a *dependencies key."""
    out = []
    in_dep_block = False
    for raw in (patch or "").splitlines():
        line = raw.rstrip("\n")
        body = line[1:] if line[:1] in "+- " else line
        # block boundaries (counted on any context/added line)
        stripped = body.strip()
        if any(f'"{b}"' in stripped and stripped.endswith("{") for b in DEP_BLOCKS):
            in_dep_block = True
            continue
        if in_dep_block and stripped.startswith("}"):
            in_dep_block = False
            continue
        if not in_dep_block:
            continue
        m = ADDED_DEP_RE.match(line)
        if m:
            name, spec = m.group(1), m.group(2)
            if name in DEP_BLOCKS:
                continue
            out.append((name, spec))
    return out


def npm_exists(name: str) -> bool | None:
    """True/False if the package name is/ isn't on the npm registry; None on
    a network/other error (do not count as a hallucination)."""
    enc = quote(name, safe="@")  # keep @scope, encode the slash
    enc = enc.replace("/", "%2F")
    url = f"{NPM_REGISTRY}/{enc}"
    req = Request(url, headers={"User-Agent": "ASG-npm-probe", "Accept": "application/json"})
    try:
        with urlopen(req, timeout=20) as r:
            return r.status == 200
    except HTTPError as e:
        if e.code == 404:
            return False
        return None
    except Exception:
        return None


def osv_npm_hit(name: str) -> bool | None:
    """True if OSV returns >=1 advisory for the npm package, False if none,
    None on error."""
    payload = json.dumps({"package": {"ecosystem": "npm", "name": name}}).encode()
    req = Request(OSV_API, data=payload,
                  headers={"User-Agent": "ASG-npm-probe", "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
            return bool(data.get("vulns"))
    except Exception:
        return None


def search_npm_dep_prs(token: str, target: int) -> list[dict]:
    """Search agent-authored merged JS/TS PRs and keep those that touch
    package.json, until `target` are collected. Returns PR records with the
    package.json patch attached."""
    kept = []
    seen = set()
    for agent, qual in AGENT_QUERIES:
        if len(kept) >= target:
            break
        for lang in LANGS:
            if len(kept) >= target:
                break
            q = f"is:pr is:merged language:{lang} {qual}"
            url = f"https://api.github.com/search/issues?q={quote(q)}&per_page=20&page=1"
            res = gh_request(url, token)
            items = res.get("items", []) if isinstance(res, dict) else []
            for it in items:
                if len(kept) >= target:
                    break
                pr = (it.get("pull_request") or {}).get("url")
                html = it.get("html_url")
                if not pr or html in seen:
                    continue
                seen.add(html)
                files = get_pr_files(pr, token)
                pj = next((f for f in files
                           if (f.get("filename") or "").rsplit("/", 1)[-1] == NPM_MANIFEST), None)
                if pj is None:
                    continue
                kept.append({
                    "agent": agent, "lang": lang, "html_url": html,
                    "package_json_path": pj.get("filename"),
                    "patch": pj.get("patch") or "",
                })
                print(f"  [{len(kept)}/{target}] {agent} {lang}: {html}", flush=True)
                time.sleep(1)
            time.sleep(2)
    return kept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=40,
                    help="number of real package.json-change PRs to probe")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parent.parent / "results" / "npm_cleanliness_probe.json")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    ap.add_argument("--token-file", default=os.path.expanduser("~/.gh_token"))
    args = ap.parse_args()

    if not args.token and Path(args.token_file).exists():
        args.token = Path(args.token_file).read_text().strip()
        print(f"[+] token from {args.token_file} (len={len(args.token)})")
    if not args.token:
        print("GITHUB_TOKEN not set -- GitHub search/files need it. "
              "export GITHUB_TOKEN=... (public_repo) and re-run.", file=sys.stderr)
        sys.exit(1)

    print(f"[1/2] searching for {args.target} real package.json-change agent PRs...")
    prs = search_npm_dep_prs(args.token, args.target)
    print(f"  collected {len(prs)} PRs with a package.json diff\n")

    print(f"[2/2] probing semver / registry / OSV on the declared deps...")
    spec_buckets: dict[str, int] = {}
    uniq_names: dict[str, dict] = {}
    n_specs = 0
    for pr in prs:
        deps = parse_added_deps(pr["patch"])
        pr["n_added_deps"] = len(deps)
        for name, spec in deps:
            n_specs += 1
            b = classify_spec(spec)
            spec_buckets[b] = spec_buckets.get(b, 0) + 1
            if name not in uniq_names:
                uniq_names[name] = {"spec_example": spec, "bucket": b}

    # registry + OSV on the unique names (dedup to spare the APIs)
    for name, rec in uniq_names.items():
        rec["npm_exists"] = npm_exists(name)
        time.sleep(0.2)
        rec["osv_hit"] = osv_npm_hit(name)
        time.sleep(0.2)

    n_names = len(uniq_names)
    resolvable = sum(v for k, v in spec_buckets.items() if k in RESOLVABLE)
    exists_true = sum(1 for r in uniq_names.values() if r["npm_exists"] is True)
    exists_false = sum(1 for r in uniq_names.values() if r["npm_exists"] is False)
    exists_err = sum(1 for r in uniq_names.values() if r["npm_exists"] is None)
    osv_true = sum(1 for r in uniq_names.values() if r["osv_hit"] is True)
    osv_known = sum(1 for r in uniq_names.values() if r["osv_hit"] is not None)

    result = {
        "n_prs_probed": len(prs),
        "n_specs": n_specs,
        "n_unique_names": n_names,
        "semver": {
            "buckets": spec_buckets,
            "resolvable": resolvable,
            "resolvable_rate": round(resolvable / max(n_specs, 1), 3),
            "resolvable_def": sorted(RESOLVABLE),
        },
        "registry": {
            "exists_true": exists_true,
            "exists_false": exists_false,
            "error": exists_err,
            "exists_rate": round(exists_true / max(exists_true + exists_false, 1), 3),
        },
        "osv": {
            "hit_true": osv_true,
            "checked": osv_known,
            "hit_rate": round(osv_true / max(osv_known, 1), 3),
        },
        "by_agent": _by_agent(prs),
        "interpretation": _verdict(resolvable / max(n_specs, 1),
                                   exists_true, exists_false, osv_true, osv_known),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))

    print("\n=== npm cleanliness probe ===")
    print(f"PRs probed: {len(prs)}  unique dep names: {n_names}  specs: {n_specs}")
    print(f"semver resolvable: {resolvable}/{n_specs} = {result['semver']['resolvable_rate']:.0%}")
    print(f"  buckets: {spec_buckets}")
    print(f"registry exists: {exists_true} yes / {exists_false} no / {exists_err} err")
    print(f"OSV hit: {osv_true}/{osv_known} = {result['osv']['hit_rate']:.0%}")
    print(f"verdict: {result['interpretation']}")
    print(f"-> {args.out}")


def _by_agent(prs):
    out = {}
    for pr in prs:
        out[pr["agent"]] = out.get(pr["agent"], 0) + 1
    return out


def _verdict(resolvable_rate, exists_true, exists_false, osv_true, osv_known):
    flags = []
    if resolvable_rate >= 0.80:
        flags.append("GREEN semver (F2 portable)")
    elif resolvable_rate >= 0.60:
        flags.append("AMBER semver (F2 needs a range resolver)")
    else:
        flags.append("RED semver (high wildcard/git share -> F2 noisy)")
    if (exists_true + exists_false) >= 1:
        flags.append("registry deterministic (F1 portable)")
    if osv_known >= 1 and osv_true >= 1:
        flags.append("OSV returns npm advisories (F3 evidence present)")
    elif osv_known >= 1:
        flags.append("OSV empty on this sample (F3 density unclear -> widen sample)")
    return "; ".join(flags)


if __name__ == "__main__":
    main()

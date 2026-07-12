#!/usr/bin/env python3
"""npm_risk_label -- automated, PR-time-anchored F1/F2/F3 risk labeling for npm.

A faithful npm port of the PyPI naturalistic-prevalence labeling
(pipeline/tse_gap_closure/label_A.py + pipeline/evidence/*). Operationalization
is matched 1:1 so the cross-ecosystem comparison cannot be attacked on changed
definitions:

  unit       = dependency CHANGE (add + version_change); removals excluded.
  parse      = STRUCTURAL (json.loads of the actual old/new package.json), so a
               root "version"/"name" or a "scripts" entry is never a dependency,
               and protocol/VCS/url/workspace specs are dropped (npm_dep_extract).
  F1 (P1)    = package did not exist on npm AT PR TIME (created > pr_time, or 404).
  F2 (P2)    = an EXACT pin whose exact version was not published AT PR TIME.
  F3 (P3)    = an OSV/GHSA advisory DISCLOSED BEFORE THE PR covers the version npm
               would install (max-satisfying over versions published <= pr_time).
  severity   = most-severe-wins F1 > F2 > F3 > NONE.

Fully automated, deterministic public evidence; no human labeling, no kappa
([[asg-no-human-evaluation]]) -- it inherits the already-validated PyPI labeling
scheme (submitted Cohen kappa = 0.90) unchanged. Registry + OSV are
unauthenticated; a GitHub token is needed only to fetch the old/new package.json
(structural parse). Resumable + storage-minimal (per-PR changes cache + slim
registry/OSV caches; never the full manifests or registry docs).

Usage:
  python -m pipeline.npm_risk_label --in results/aidev_npm_sample.jsonl \
      --token-file /path/to/.ghtok
"""
from __future__ import annotations

import argparse
import base64
import collections
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(__file__))
from aidev_collect import gh_request, API                       # noqa: E402
from npm_dep_extract import diff_changes, is_exact_pin          # noqa: E402
from npm_evidence import reconstruct, advisory_ids_at_pr        # noqa: E402
from npm_semver import parse_version, is_prerelease, UNPARSEABLE  # noqa: E402


def _latest_at_pr(versions_at_pr):
    """Highest non-prerelease version published by PR time (what '*'/'latest'
    installs)."""
    rel = [(parse_version(v), v) for v in versions_at_pr
           if parse_version(v) and not is_prerelease(v)]
    return max(rel)[1] if rel else None


def _pinned_absent(pinned, versions_at_pr):
    pt = parse_version(pinned)
    for v in versions_at_pr:
        if v == pinned or (pt is not None and parse_version(v) == pt):
            return False
    return True


# ---- GitHub: fetch old/new package.json for a structural diff ----------------

def _repo_full(repository_url: str) -> str:
    return repository_url.replace("https://api.github.com/repos/", "").strip("/")


def _file_at(repo: str, path: str, ref: str, token: str):
    """Decoded text of `path` at `ref`, or None if absent (404) / error."""
    url = f"{API}/repos/{repo}/contents/{quote(path)}?ref={ref}"
    res = gh_request(url, token)
    if not isinstance(res, dict) or res.get("encoding") != "base64":
        return None
    try:
        return base64.b64decode(res["content"]).decode("utf-8", errors="replace")
    except Exception:
        return None


def pr_changes(pr: dict, token: str) -> list[dict]:
    """Structural add/version_change list for one collected PR (across all its
    package.json manifests). Fetches base/head package.json and diffs them."""
    detail = gh_request(pr["pr_api_url"], token)
    if not isinstance(detail, dict):
        return []
    base_sha = (detail.get("base") or {}).get("sha")
    head_sha = (detail.get("head") or {}).get("sha")
    if not head_sha:
        return []
    repo = _repo_full(pr["repository_url"])
    changes = []
    for mani in pr.get("dep_changes", []):
        path = mani.get("path")
        if not path or not path.endswith("package.json"):
            continue
        new_text = _file_at(repo, path, head_sha, token)
        old_text = _file_at(repo, path, base_sha, token) if base_sha else ""
        if new_text is None:
            continue
        for c in diff_changes(old_text or "", new_text):
            c["file"] = path
            changes.append(c)
    return changes


# ---- per-change verdict (PyPI decide_primary analogue) -----------------------

def decide(change, ev, pr_time, osv_cache):
    """(label, risky, resolved_version, osv_ids, note). Most-severe-wins."""
    name, spec = change["name"], change["spec"]
    exists = ev["exists_at_pr"]
    if exists is None:
        return "NONE", False, None, [], "existence undeterminable"
    if exists is False:
        return "F1", True, None, [], "package absent at PR time"

    pinned = is_exact_pin(spec)
    if pinned and _pinned_absent(pinned, ev["versions_at_pr"]):
        return "F2", True, None, [], f"exact pin {pinned} not published at PR time"

    resolved = ev["resolved"]
    ver = resolved if (resolved and resolved != UNPARSEABLE) else _latest_at_pr(ev["versions_at_pr"])
    if ver:
        ids = advisory_ids_at_pr(name, ver, pr_time, osv_cache)
        if ids:
            return "F3", True, ver, ids, "advisory disclosed before PR"
    return "NONE", False, ver, [], "no PR-time risk evidence"


# ---- driver ------------------------------------------------------------------

def main():
    here = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, default=here / "results" / "aidev_npm_sample.jsonl")
    ap.add_argument("--out-detail", type=Path, default=here / "results" / "npm_risk_labels.jsonl")
    ap.add_argument("--out-agg", type=Path, default=here / "results" / "npm_risk_labels.json")
    ap.add_argument("--changes-cache", type=Path, default=here / "results" / "npm_changes_cache.json")
    ap.add_argument("--reg-cache", type=Path, default=here / "results" / "npm_reg_cache.json")
    ap.add_argument("--osv-cache", type=Path, default=here / "results" / "npm_osv_cache.json")
    ap.add_argument("--token-file", type=Path, default=Path.home() / ".gh_token")
    ap.add_argument("--token", default=None)
    args = ap.parse_args()

    token = args.token or (args.token_file.read_text().strip() if args.token_file.exists() else None)
    if not token:
        print("no GitHub token (need --token/--token-file to fetch package.json)", file=sys.stderr)
        sys.exit(1)

    if not args.inp.exists():
        print(f"input not found: {args.inp}", file=sys.stderr)
        sys.exit(1)
    prs = [json.loads(l) for l in args.inp.read_text().splitlines() if l.strip()]
    print(f"[+] {len(prs)} collected PRs from {args.inp}")

    def _load(p):
        return json.loads(p.read_text()) if p.exists() else {}
    changes_cache = _load(args.changes_cache)   # pr_url -> [changes] (structural, GitHub)
    reg_cache = _load(args.reg_cache)           # name -> slim registry | None
    osv_cache = _load(args.osv_cache)           # name -> slim osv | None
    print(f"[resume] changes={len(changes_cache)} reg={len(reg_cache)} osv={len(osv_cache)}")

    detail_f = args.out_detail.open("w", encoding="utf-8")
    pr_recs = []
    n_changes = 0
    ct_mix = collections.Counter()
    label_counts = collections.Counter()

    for i, pr in enumerate(prs):
        url = pr["html_url"]
        if url in changes_cache:
            changes = changes_cache[url]
        else:
            changes = pr_changes(pr, token)
            changes_cache[url] = changes
        pr_time = pr.get("created_at")

        pr_labels = []
        for c in changes:
            n_changes += 1
            ct_mix[c["change_type"]] += 1
            ev = reconstruct(c["name"], c["spec"], pr_time, reg_cache)
            label, risky, ver, ids, note = decide(c, ev, pr_time, osv_cache)
            label_counts[label] += 1
            pr_labels.append(label)
            detail_f.write(json.dumps({
                "pr": url, "agent": pr.get("agent"), "repo": _repo_full(pr["repository_url"]),
                "name": c["name"], "spec": c["spec"], "block": c["block"],
                "change_type": c["change_type"], "label": label,
                "resolved": ver, "osv_ids": ids, "note": note,
            }, ensure_ascii=False) + "\n")

        pr_recs.append({
            "pr": url, "agent": pr.get("agent"), "repo": _repo_full(pr["repository_url"]),
            "n_changes": len(changes),
            "F1": "F1" in pr_labels, "F2": "F2" in pr_labels, "F3": "F3" in pr_labels,
            "any_risk": any(x in ("F1", "F2", "F3") for x in pr_labels),
        })
        if (i + 1) % 25 == 0:
            args.changes_cache.write_text(json.dumps(changes_cache, ensure_ascii=False))
            args.reg_cache.write_text(json.dumps(reg_cache, ensure_ascii=False))
            args.osv_cache.write_text(json.dumps(osv_cache, ensure_ascii=False))
            print(f"  [{i+1}/{len(prs)}] changes={n_changes} reg={len(reg_cache)} osv={len(osv_cache)}",
                  flush=True)
    detail_f.close()
    args.changes_cache.write_text(json.dumps(changes_cache, ensure_ascii=False))
    args.reg_cache.write_text(json.dumps(reg_cache, ensure_ascii=False))
    args.osv_cache.write_text(json.dumps(osv_cache, ensure_ascii=False))

    agg = _aggregate(pr_recs, n_changes, ct_mix, label_counts)
    args.out_agg.write_text(json.dumps(agg, indent=2))

    print("\n=== npm PR-time-anchored F1/F2/F3 prevalence (PyPI-matched operationalization) ===")
    print(f"changes (add+version_change): {n_changes}   change_mix={dict(ct_mix)}")
    cl = agg["change_level_prevalence"]
    for k in ("any_risk", "F1", "F2", "F3"):
        print(f"  {k:9} {cl[k]['count']:4d} / {n_changes}  = {cl[k]['rate']:.2%}")
    pp = agg["pr_level_prevalence"]
    print(f"PRs with >=1 evaluable change: {agg['n_prs_with_changes']}/{agg['n_prs_total']}; "
          f"any-risk PRs = {pp['any_risk']['count']} ({pp['any_risk']['rate']:.2%})")
    print(f"detail -> {args.out_detail}\naggregate -> {args.out_agg}")


def _aggregate(pr_recs, n_changes, ct_mix, label_counts):
    with_changes = [r for r in pr_recs if r["n_changes"] > 0]
    n_pd = len(with_changes)

    def crate(label):
        c = label_counts.get(label, 0)
        return {"count": c, "rate": round(c / max(n_changes, 1), 4)}

    risky_changes = sum(label_counts.get(k, 0) for k in ("F1", "F2", "F3"))

    def prate(pred):
        c = sum(1 for r in with_changes if pred(r))
        return {"count": c, "rate": round(c / max(n_pd, 1), 4)}

    by_agent = {}
    for r in with_changes:
        d = by_agent.setdefault(r["agent"] or "unknown", {"prs": 0, "any_risk": 0})
        d["prs"] += 1
        d["any_risk"] += 1 if r["any_risk"] else 0
    for d in by_agent.values():
        d["prevalence"] = round(d["any_risk"] / max(d["prs"], 1), 4)

    # repo clustering robustness: collapse to one any-risk flag per repo
    repos = collections.defaultdict(lambda: {"prs": 0, "any_risk": False})
    for r in with_changes:
        repos[r["repo"]]["prs"] += 1
        repos[r["repo"]]["any_risk"] = repos[r["repo"]]["any_risk"] or r["any_risk"]
    n_repos = len(repos)
    repos_any = sum(1 for v in repos.values() if v["any_risk"])

    return {
        "operationalization": "PyPI-matched: structural parse, PR-time anchoring, "
                              "change-level unit, most-severe-wins F1>F2>F3, removals excluded",
        "n_prs_total": len(pr_recs),
        "n_prs_with_changes": n_pd,
        "n_changes": n_changes,
        "change_type_mix": dict(ct_mix),
        "change_level_prevalence": {
            "any_risk": {"count": risky_changes, "rate": round(risky_changes / max(n_changes, 1), 4)},
            "F1": crate("F1"), "F2": crate("F2"), "F3": crate("F3"),
            "NONE": crate("NONE"),
        },
        "pr_level_prevalence": {
            "any_risk": prate(lambda r: r["any_risk"]),
            "F1": prate(lambda r: r["F1"]), "F2": prate(lambda r: r["F2"]),
            "F3": prate(lambda r: r["F3"]),
        },
        "repo_level": {"n_repos": n_repos, "repos_any_risk": repos_any,
                       "rate": round(repos_any / max(n_repos, 1), 4)},
        "by_agent": by_agent,
        "note": "fully automated, no human labeling; inherits PyPI labeling scheme (kappa=0.90)",
    }


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""aidev_npm_yield -- feasibility yield check for an npm prevalence study.

Before committing to a full npm collection, measure (a) how many AI-agent merged PRs
exist for JavaScript/TypeScript per agent (search total_count, cheap), and (b) what
fraction of a sample actually change package.json dependencies. Projects the npm
dep-change PR yield to decide go/no-go. Reuses aidev_collect helpers; pure stdlib.

Token from $GITHUB_TOKEN (never on argv).
"""
import json
import os
import sys
import time
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

sys.path.insert(0, os.path.dirname(__file__))
from aidev_collect import gh_request, get_pr_files, AGENT_QUERIES  # noqa: E402

API = "https://api.github.com"
NPM_MANIFESTS = {"package.json"}
LANGS = ["JavaScript", "TypeScript"]


def search_total(qualifier, lang, token):
    q = f"is:pr is:merged language:{lang} {qualifier}"
    url = f"{API}/search/issues?q={quote(q)}&per_page=20&page=1"
    res = gh_request(url, token)
    if not isinstance(res, dict):
        return 0, []
    return res.get("total_count", 0), res.get("items", [])


def npm_change(files):
    for f in files:
        name = (f.get("filename") or "").rsplit("/", 1)[-1]
        if name in NPM_MANIFESTS:
            return True
    return False


def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN not set", file=sys.stderr)
        sys.exit(1)
    out = {"per_agent": {}, "sample_npm_change": {}}
    seen_total = {}
    sample_pool = []
    for agent, qual in AGENT_QUERIES:
        tot = 0
        items = []
        for lang in LANGS:
            t, it = search_total(qual, lang, token)
            tot += t
            items += it
            time.sleep(2)
        prev = seen_total.get(agent, 0)
        seen_total[agent] = prev + tot
        out["per_agent"][agent] = seen_total[agent]
        # collect a few PR api urls for sampling
        for it in items[:8]:
            pr = (it.get("pull_request") or {}).get("url")
            if pr:
                sample_pool.append((agent, pr))
        print(f"[{agent}] {qual[:30]:30} JS+TS total so far: {seen_total[agent]}", flush=True)

    # sample package.json-change rate
    print(f"\nsampling {min(len(sample_pool), 60)} PRs for package.json dep changes...", flush=True)
    n_s = nc = 0
    for agent, pr in sample_pool[:60]:
        files = get_pr_files(pr, token)
        n_s += 1
        if npm_change(files):
            nc += 1
        time.sleep(1)
    out["sample_npm_change"] = {"sampled": n_s, "with_package_json": nc,
                                "rate": round(nc / max(n_s, 1), 3)}
    total_prs = sum(out["per_agent"].values())
    proj = int(total_prs * out["sample_npm_change"]["rate"])
    out["projection"] = {"total_js_ts_prs": total_prs,
                         "est_package_json_change_prs": proj,
                         "note": ">=500 dep-change PRs -> npm prevalence worth the ~2wk study"}
    json.dump(out, open("results/aidev_npm_yield.json", "w"), indent=2)
    print(f"\n=== YIELD ===")
    print(f"total JS+TS agent PRs: {total_prs}")
    print(f"package.json-change rate (sample): {nc}/{n_s} = {100*nc/max(n_s,1):.0f}%")
    print(f"projected dep-change PRs: ~{proj}")
    print(f"-> results/aidev_npm_yield.json")


if __name__ == "__main__":
    main()

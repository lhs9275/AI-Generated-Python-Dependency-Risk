"""Expand the naturalistic corpus via GitHub search for AI-agent dependency PRs.

The AIDev candidate pool is a real source of AI-agent PRs but only a small
fraction touch a dependency manifest. To reach a corpus large enough for paired
gate analysis, we additionally search GitHub for **AI-coding-agent-authored PRs
that mention a Python dependency manifest** and keep the ones that actually
changed one.

Selection independence (command 0 / 3.1 / line 107): every query identifies a PR
by (a) AI authorship and (b) a dependency-manifest term ONLY. No query mentions a
risk family, a package, a version, or a vulnerability. Selection therefore cannot
be biased toward cases the guard can catch.

AI-authorship signals used (each is an unambiguous AI coding agent):
  copilot : author:app/copilot-swe-agent     (GitHub Copilot coding agent)
  devin   : author:app/devin-ai-integration  (Devin)
  aider   : "Generated with" + aider          (aider commit/PR signature)
  cursor  : "co-authored-by: cursor"          (Cursor agent co-author trailer)

Output: a JSONL of PR records in the embedded-``dep_changes`` shape consumed by
``collect_prs`` (fields: agent, html_url, pr_api_url, repository_url, created_at,
merged_at, user, dep_changes). Cached file responses are shared with collect_prs.
"""

import argparse
import json
import re
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pipeline.real_pr_mining.normalize_manifest_diff import detect_manifest_type
from pipeline.tse_gap_closure.collect_prs import _gh_files, _files_to_dep_changes

# Manifest terms that bias selection toward dependency-changing PRs (NOT risk).
MANIFEST_TERMS = ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]

# (tool, query-prefix). The manifest term is appended per term.
TOOL_QUERIES = [
    ("copilot", "is:pr author:app/copilot-swe-agent"),
    ("devin", "is:pr author:app/devin-ai-integration"),
    ("aider", 'is:pr "Generated with" aider'),
    ("cursor", 'is:pr "co-authored-by: cursor"'),
]

_REPO_RE = re.compile(r"github\.com/([^/]+/[^/]+)/pull/(\d+)")


def _search_page(query, page, per_page=100, pause=2.2):
    """One page of the issues/PR search API. Returns list of items (PR issues)."""
    time.sleep(pause)  # stay under the 30 req/min search limit
    cmd = ["gh", "api", "-X", "GET", "search/issues",
           "-f", f"q={query}", "-f", f"per_page={per_page}", "-f", f"page={page}",
           "--jq", ".items"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return []
    if res.returncode != 0:
        return []
    try:
        return json.loads(res.stdout or "[]")
    except json.JSONDecodeError:
        return []


def _to_api_url(html_url):
    m = _REPO_RE.search(html_url or "")
    if not m:
        return None, None
    repo, num = m.group(1), m.group(2)
    return f"https://api.github.com/repos/{repo}/pulls/{num}", repo


def search_candidates(max_pages, per_repo_cap, search_pause):
    """Search every (tool, manifest-term) pair; return de-duped PR candidates.

    Each candidate is metadata only at this point; ``dep_changes`` is filled in
    by the file-fetch step. Per-repo cap keeps any single repository from
    dominating the corpus (repo-diversity target, command 3.2).
    """
    seen = {}            # html_url -> candidate
    per_repo = defaultdict(int)
    for tool, prefix in TOOL_QUERIES:
        for term in MANIFEST_TERMS:
            query = f"{prefix} {term}"
            for page in range(1, max_pages + 1):
                items = _search_page(query, page, pause=search_pause)
                if not items:
                    break
                added = 0
                for it in items:
                    html = it.get("html_url") or ""
                    if "/pull/" not in html or html in seen:
                        continue
                    api_url, repo = _to_api_url(html)
                    if not api_url:
                        continue
                    if per_repo[repo] >= per_repo_cap:
                        continue
                    per_repo[repo] += 1
                    added += 1
                    seen[html] = {
                        "agent": tool,
                        "html_url": html,
                        "pr_api_url": api_url,
                        "repository_url": f"https://api.github.com/repos/{repo}",
                        "created_at": it.get("created_at"),
                        "merged_at": (it.get("pull_request") or {}).get("merged_at"),
                        "user": (it.get("user") or {}).get("login"),
                        "_query": query,
                    }
                print(f"  [{tool}|{term}] page {page}: +{added} (total {len(seen)})",
                      flush=True)
                if len(items) < 100:
                    break
    return list(seen.values())


def _api_parts(api_url):
    m = re.search(r"/repos/([^/]+)/([^/]+)/pulls/(\d+)", api_url or "")
    return (m.group(1), m.group(2), m.group(3)) if m else (None, None, None)


def fetch_and_filter(candidates, cache_dir, workers):
    """Fetch each candidate's files (1 page), keep only manifest-changing PRs."""
    cache_dir = Path(cache_dir)

    def task(c):
        owner, repo, num = _api_parts(c["pr_api_url"])
        if not owner:
            return None
        files = _gh_files(owner, repo, num, cache_dir / f"{owner}__{repo}__{num}.json",
                          max_pages=1)
        if isinstance(files, dict) and "_error" in files:
            return None
        dep = _files_to_dep_changes(files)
        if not any(detect_manifest_type(d["path"]) for d in dep):
            return None
        c = dict(c)
        c["dep_changes"] = dep
        c["n_files_total"] = len(files)
        return c

    out = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(task, c) for c in candidates]
        for fut in as_completed(futs):
            done += 1
            r = fut.result()
            if r:
                out.append(r)
            if done % 100 == 0:
                print(f"  fetched {done}/{len(candidates)}; kept {len(out)}", flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="results/tse_gap_closure_github_prs.jsonl")
    ap.add_argument("--cache-dir", default="outputs/tse_gap_closure/data/pr_files_cache")
    ap.add_argument("--max-pages", type=int, default=4,
                    help="search pages per (tool, manifest-term) pair (100 PRs/page)")
    ap.add_argument("--per-repo-cap", type=int, default=4,
                    help="max PRs kept per repository (repo-diversity)")
    ap.add_argument("--search-pause", type=float, default=2.2)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    print("[expand] searching GitHub for AI-agent dependency PRs...", flush=True)
    cands = search_candidates(args.max_pages, args.per_repo_cap, args.search_pause)
    print(f"[expand] {len(cands)} unique candidate PRs across "
          f"{len({_api_parts(c['pr_api_url'])[:2] for c in cands})} repos", flush=True)

    print("[expand] fetching diffs + filtering to manifest changes...", flush=True)
    kept = fetch_and_filter(cands, args.cache_dir, args.workers)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for r in kept:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"[expand] kept {len(kept)} dependency-changing AI PRs -> {args.out}")
    print(f"[expand] by tool: {dict(Counter(c['agent'] for c in kept))}")
    repos = {_api_parts(c['pr_api_url'])[:2] for c in kept}
    print(f"[expand] repos: {len(repos)}")


if __name__ == "__main__":
    main()

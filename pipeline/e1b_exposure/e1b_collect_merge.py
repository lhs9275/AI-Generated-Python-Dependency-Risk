#!/usr/bin/env python3
"""e1b_collect_merge -- fetch real-world PR merge outcomes for the naturalistic corpus.

Workstream E1b ("Real-World Exposure Linkage"). This is step 1 of 3.

WHY: the controlled intervention (open-weight models) and the prevalence study
(deployed commercial agents) are measured on DISJOINT generator sets. E1b links
them OBSERVATIONALLY on the prevalence population by asking, for the same
agent-authored PRs whose dependency risk we labeled, what actually happened to
the PR (merged / closed / open). It does NOT and CANNOT establish a causal
merge-rate effect of the gate -- the gate never intervened on these PRs. It only
quantifies the real-world exposure that the gate's BLOCK set would have flagged.

This script reads the per-change patch records (which carry pr_id / pr_url /
repo_full_name) and, for each UNIQUE PR, queries the GitHub REST API for its
merge state. Results are cached so the run is resumable and the downstream
analysis is offline.

Auth: set GITHUB_TOKEN in the environment (a fine-grained or classic PAT with
public_repo read is enough). DO NOT pass the token on the command line and DO
NOT commit it. Unauthenticated runs are rate-limited to 60 req/h and will crawl.

Pure stdlib (json, urllib, argparse, time, os).

Example:
  export GITHUB_TOKEN=ghp_xxx
  python pipeline/e1b_exposure/e1b_collect_merge.py \
    --input results/tse_gap_closure/data/dependency_change_patches.jsonl \
    --output results/e1b_exposure/pr_outcomes.jsonl
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def parse_pr(rec):
    """Return (owner, repo, number) from a change record, or None."""
    url = rec.get("pr_url") or ""
    # https://github.com/<owner>/<repo>/pull/<n>
    if "/pull/" in url:
        try:
            tail = url.split("github.com/", 1)[1]
            owner_repo, num = tail.split("/pull/", 1)
            owner, repo = owner_repo.split("/", 1)
            return owner, repo, int(num.split("/")[0].split("#")[0])
        except Exception:
            pass
    # fallback: pr_id like "owner/repo#n"
    pid = rec.get("pr_id") or ""
    if "#" in pid and "/" in pid:
        try:
            owner_repo, num = pid.rsplit("#", 1)
            owner, repo = owner_repo.split("/", 1)
            return owner, repo, int(num)
        except Exception:
            pass
    return None


def gh_get(path, token):
    """GET an API path with auth + rate-limit handling. Returns (status, json)."""
    req = urllib.request.Request(API + path)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "asg-e1b-exposure")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                remaining = r.headers.get("X-RateLimit-Remaining")
                reset = r.headers.get("X-RateLimit-Reset")
                if remaining is not None and int(remaining) <= 1 and reset:
                    wait = max(0, int(reset) - int(time.time())) + 2
                    log(f"  rate-limit low; sleeping {wait}s")
                    time.sleep(wait)
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return 404, None
            if e.code in (403, 429):
                reset = e.headers.get("X-RateLimit-Reset")
                retry = e.headers.get("Retry-After")
                if retry:
                    wait = int(retry) + 1
                elif reset:
                    wait = max(0, int(reset) - int(time.time())) + 2
                else:
                    wait = 60 * (attempt + 1)
                log(f"  {e.code} rate/secondary limit; sleeping {wait}s")
                time.sleep(wait)
                continue
            if 500 <= e.code < 600:
                time.sleep(5 * (attempt + 1))
                continue
            return e.code, None
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (attempt + 1))
    return -1, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="results/tse_gap_closure/data/dependency_change_patches.jsonl",
                    help="per-change patch jsonl (must carry pr_url/pr_id/repo_full_name)")
    ap.add_argument("--output", default="results/e1b_exposure/pr_outcomes.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="smoke test: only N PRs (0=all)")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        log("WARN: GITHUB_TOKEN not set -- unauthenticated 60 req/h limit. Export a PAT.")

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    # collect unique PRs
    prs = {}
    with open(args.input, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            pid = rec.get("pr_id")
            if not pid or pid in prs:
                continue
            parsed = parse_pr(rec)
            if parsed:
                prs[pid] = {"pr_id": pid, "owner": parsed[0], "repo": parsed[1],
                            "number": parsed[2], "repo_full_name": rec.get("repo_full_name"),
                            "agent_name": rec.get("agent_name"),
                            "created_at": rec.get("created_at")}
    log(f"unique PRs to resolve: {len(prs)}")

    # resume: load already-fetched ids
    done = {}
    if os.path.exists(args.output):
        with open(args.output, encoding="utf-8") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                    done[o["pr_id"]] = True
                except Exception:
                    pass
        log(f"resume: {len(done)} already fetched")

    todo = [p for pid, p in prs.items() if pid not in done]
    if args.limit:
        todo = todo[:args.limit]

    with open(args.output, "a", encoding="utf-8") as out:
        for i, p in enumerate(todo, 1):
            status, data = gh_get(f"/repos/{p['owner']}/{p['repo']}/pulls/{p['number']}", token)
            rec = {"pr_id": p["pr_id"], "agent_name": p["agent_name"],
                   "created_at": p["created_at"], "http_status": status}
            if status == 200 and data:
                rec.update({
                    "state": data.get("state"),                       # open|closed
                    "merged": bool(data.get("merged_at")),
                    "merged_at": data.get("merged_at"),
                    "closed_at": data.get("closed_at"),
                    "merge_commit_sha": data.get("merge_commit_sha"),
                    "additions": data.get("additions"),
                    "deletions": data.get("deletions"),
                    "changed_files": data.get("changed_files"),
                    "repo_stars": (data.get("base") or {}).get("repo", {}).get("stargazers_count"),
                    "repo_forks": (data.get("base") or {}).get("repo", {}).get("forks_count"),
                    "author_assoc": data.get("author_association"),
                })
            else:
                rec["state"] = "unknown"
                rec["merged"] = None
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            if i % 50 == 0:
                log(f"  {i}/{len(todo)}")

    log(f"done. wrote outcomes -> {args.output}")


if __name__ == "__main__":
    main()

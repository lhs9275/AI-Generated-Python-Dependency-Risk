"""Collect a NATURALISTIC corpus of AI-assisted dependency-changing PRs.

Independent of the controlled benchmark: PRs come from the AIDev real-world
AI-agent PR pool (aider/devin/cursor/claude-code/codex/continue), screened ONLY
for (a) AI-assisted authorship and (b) a Python dependency-manifest change. No
risk-family search term is used (command 0/3.1), so selection cannot be biased
toward cases the guard can catch.

Pipeline:
  1. Load every candidate PR (metadata pool) + any PR that already carries an
     embedded ``dep_changes`` diff (the already-fetched routine-corpus source).
  2. For PRs without an embedded diff, fetch ``/pulls/<n>/files`` from the GitHub
     API (``gh api``), keep the patches of recognized manifest files, and cache
     the raw response to disk so the run is resumable and reproducible.
  3. Extract manifest-aware dependency-change rows with the battle-tested
     ``pipeline.real_pr_mining.extract_dependency_changes.extract_rows``.
  4. Apply inclusion/exclusion criteria (command 3.3/3.4) and emit:
       data/raw_pr_index.csv              every screened PR + disposition
       data/sampled_prs.csv               included dependency-changing PRs
       data/dependency_change_patches.jsonl  one row per dependency change
     plus a machine-readable collection log (search queries, API limits,
     exclusion counts) for the README.

Usage:
  python3 -m pipeline.tse_gap_closure.collect_prs \
      --candidates results/aidev_sample_scaleup.candidates.jsonl \
      --embedded results/aidev_sample_scaleup.jsonl results/aidev_sample_v2.jsonl results/aidev_sample.jsonl \
      --out-dir outputs/tse_gap_closure/data \
      --workers 8
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.real_pr_mining.extract_dependency_changes import (  # noqa: E402
    extract_rows,
    pr_has_manifest_change,
)
from pipeline.real_pr_mining.normalize_manifest_diff import detect_manifest_type  # noqa: E402
from pipeline.real_pr_mining.classify_pr_type import classify_pr_type  # noqa: E402

# Manifest kinds that yield parseable package rows (lock files are recognized as
# a manifest change but produce no package rows by design).
PKG_BEARING = {"requirements_txt", "requirements_dir", "pyproject_toml",
               "setup_py", "setup_cfg", "pipfile"}

_API_RE = re.compile(r"/repos/([^/]+)/([^/]+)/pulls/(\d+)")


def _pr_url(rec):
    return rec.get("html_url") or rec.get("pr_api_url")


def _api_parts(rec):
    """(owner, repo, number) from a candidate's pr_api_url / html_url."""
    u = rec.get("pr_api_url") or ""
    m = _API_RE.search(u)
    if m:
        return m.group(1), m.group(2), m.group(3)
    m = re.search(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)", rec.get("html_url") or "")
    return (m.group(1), m.group(2), m.group(3)) if m else (None, None, None)


def _load_jsonl(path):
    out = {}
    txt = Path(path).read_text(encoding="utf-8").strip()
    if not txt:
        return out
    try:
        data = json.loads(txt)
        recs = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        recs = []
        for ln in txt.splitlines():
            ln = ln.strip()
            if ln:
                try:
                    recs.append(json.loads(ln))
                except json.JSONDecodeError:
                    pass
    for r in recs:
        k = _pr_url(r)
        if k:
            out.setdefault(k, r)
    return out


def _gh_files(owner, repo, number, cache_path, max_pages=3, per_page=100):
    """Fetch a PR's changed-file list (with patches) via gh api, disk-cached.

    Returns the parsed JSON list, or a dict {"_error": code} on failure.
    """
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except json.JSONDecodeError:
            pass
    files = []
    for page in range(1, max_pages + 1):
        cmd = ["gh", "api",
               f"repos/{owner}/{repo}/pulls/{number}/files",
               "-X", "GET", "-f", f"per_page={per_page}", "-f", f"page={page}"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            return {"_error": "timeout"}
        if res.returncode != 0:
            err = res.stderr.strip()
            code = "404" if "Not Found" in err else ("403" if "rate limit" in err.lower() or "403" in err else "error")
            if page == 1:
                return {"_error": code}
            break  # partial pages already collected
        try:
            page_files = json.loads(res.stdout)
        except json.JSONDecodeError:
            return {"_error": "badjson"}
        if not page_files:
            break
        files.extend(page_files)
        if len(page_files) < per_page:
            break
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(files))
    return files


def _files_to_dep_changes(files):
    """Keep only recognized-manifest files; map to the dep_changes diff shape."""
    dep = []
    for f in files:
        path = f.get("filename", "")
        if detect_manifest_type(path) is None:
            continue
        dep.append({
            "path": path,
            "additions": f.get("additions"),
            "deletions": f.get("deletions"),
            "patch": f.get("patch", "") or "",
        })
    return dep


def collect(candidates_files, embedded_files, out_dir, cache_dir, workers,
            max_fetch=None):
    out_dir = Path(out_dir)
    cache_dir = Path(cache_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Merge all PR records (embedded patches win; they already carry dep_changes).
    pool = {}
    for f in candidates_files:
        for k, v in _load_jsonl(f).items():
            pool.setdefault(k, dict(v))
    embedded_urls = set()
    for f in embedded_files:
        for k, v in _load_jsonl(f).items():
            if v.get("dep_changes"):
                pool.setdefault(k, {}).update(v)
                embedded_urls.add(k)

    # 2. Fetch diffs for PRs lacking an embedded dep_changes diff.
    need = [(k, v) for k, v in pool.items() if not v.get("dep_changes")]
    if max_fetch is not None:
        need = need[:max_fetch]
    fetch_status = {}  # url -> "embedded"|"ok"|"404"|"403"|...

    def task(kv):
        k, v = kv
        owner, repo, num = _api_parts(v)
        if not owner:
            return k, {"_error": "no_api_url"}
        safe = f"{owner}__{repo}__{num}.json"
        files = _gh_files(owner, repo, num, cache_dir / safe)
        return k, files

    print(f"[collect] pool={len(pool)} embedded={len(embedded_urls)} "
          f"to_fetch={len(need)} workers={workers}", flush=True)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(task, kv) for kv in need]
        for fut in as_completed(futs):
            k, files = fut.result()
            done += 1
            if isinstance(files, dict) and "_error" in files:
                fetch_status[k] = files["_error"]
            else:
                pool[k]["dep_changes"] = _files_to_dep_changes(files)
                pool[k]["_n_files_fetched"] = len(files)
                fetch_status[k] = "ok"
            if done % 50 == 0:
                print(f"  fetched {done}/{len(need)}", flush=True)
    for k in embedded_urls:
        fetch_status[k] = "embedded"

    # 3. Extract dependency-change rows + screen each PR.
    raw_index = []
    sampled = []
    dep_rows_all = []
    for k, v in pool.items():
        owner, repo, num = _api_parts(v)
        repo_full = f"{owner}/{repo}" if owner else None
        status = fetch_status.get(k, "embedded" if v.get("dep_changes") else "not_fetched")
        had_manifest = pr_has_manifest_change(v) if v.get("dep_changes") is not None else False
        rows = extract_rows(v) if v.get("dep_changes") else []
        n_pkg_rows = len(rows)
        # inclusion: a recognized manifest changed AND we parsed >=1 package row
        # (lock-file-only changes yield no parseable spec -> excluded per 3.4).
        if status in ("404", "403", "error", "timeout", "badjson", "no_api_url"):
            disp, reason = "excluded", f"fetch_{status}"
        elif not had_manifest:
            disp, reason = "excluded", "no_manifest_change"
        elif n_pkg_rows == 0:
            disp, reason = "excluded", "lockfile_or_unparseable_only"
        elif not v.get("created_at"):
            disp, reason = "excluded", "no_pr_time"
        else:
            disp, reason = "included", "ok"

        raw_index.append({
            "pr_url": v.get("html_url") or k,
            "repo_full_name": repo_full,
            "agent": v.get("agent"),
            "created_at": v.get("created_at"),
            "fetch_status": status,
            "had_manifest_change": had_manifest,
            "n_package_rows": n_pkg_rows,
            "disposition": disp,
            "exclude_reason": reason,
        })
        if disp != "included":
            continue

        pr_type = classify_pr_type(rows, had_manifest_change=True)
        sampled.append({
            "pr_id": rows[0]["pr_id"],
            "pr_url": v.get("html_url"),
            "repo_full_name": repo_full,
            "agent": v.get("agent"),
            "created_at": v.get("created_at"),
            "merged_at": v.get("merged_at"),
            "n_dependency_changes": n_pkg_rows,
            "pr_type": pr_type,
            "manifest_paths": "|".join(sorted({r["manifest_path"] for r in rows})),
            "tool_evidence": f"aidev_agent:{v.get('agent')}",
        })
        for r in rows:
            r["pr_type"] = pr_type
            r["tool_evidence"] = f"aidev_agent:{v.get('agent')}"
            dep_rows_all.append(r)

    # 4. Dedupe dependency-change rows (pr, manifest, package, change_type) and
    #    stamp a stable change_id used to join evidence/labels/guard downstream.
    seen, dep_rows = {}, []
    for r in dep_rows_all:
        key = (r["pr_id"], r["manifest_path"], r["normalized_package_name"], r["change_type"])
        if key not in seen:
            r["change_id"] = "::".join(str(x) for x in key)
            seen[key] = r
            dep_rows.append(r)

    # 5. Write artifacts.
    _write_csv(out_dir / "raw_pr_index.csv", raw_index)
    _write_csv(out_dir / "sampled_prs.csv", sampled)
    with (out_dir / "dependency_change_patches.jsonl").open("w", encoding="utf-8") as fh:
        for r in dep_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    # 6. Collection log (for README + reproducibility).
    incl_prs = {r["pr_url"] for r in sampled}
    log = {
        "sources": {
            "candidates_files": candidates_files,
            "embedded_files": embedded_files,
            "selection_terms": "AI-assisted authorship (AIDev agent metadata) + "
                               "Python dependency-manifest change. NO risk-family terms.",
        },
        "n_pr_pool": len(pool),
        "n_with_embedded_diff": len(embedded_urls),
        "n_fetched_from_github": sum(1 for s in fetch_status.values() if s == "ok"),
        "fetch_status_counts": dict(Counter(fetch_status.values())),
        "exclude_reason_counts": dict(Counter(r["exclude_reason"] for r in raw_index)),
        "n_included_prs": len(incl_prs),
        "n_included_repos": len({r["repo_full_name"] for r in sampled}),
        "n_tool_families": len({r["agent"] for r in sampled if r["agent"]}),
        "tool_families": sorted({r["agent"] for r in sampled if r["agent"]}),
        "n_dependency_changes": len(dep_rows),
        "manifest_mix": dict(Counter(r["manifest_type"] for r in dep_rows)),
        "change_type_mix": dict(Counter(r["change_type"] for r in dep_rows)),
        "pr_time_recoverable_frac": round(
            sum(1 for r in sampled if r["created_at"]) / max(1, len(sampled)), 4),
    }
    (out_dir / "collection_log.json").write_text(
        json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n[collect] screened {len(raw_index)} PRs -> included {log['n_included_prs']} "
          f"({log['n_included_repos']} repos, {log['n_tool_families']} tool families)")
    print(f"[collect] dependency changes: {log['n_dependency_changes']}")
    print(f"[collect] exclude reasons: {log['exclude_reason_counts']}")
    print(f"[collect] manifest mix: {log['manifest_mix']}")
    return log


def _write_csv(path, rows):
    if not rows:
        path.write_text("")
        return
    cols = list(rows[0].keys())
    with Path(path).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", nargs="+",
                    default=["results/aidev_sample_scaleup.candidates.jsonl"])
    ap.add_argument("--embedded", nargs="+",
                    default=["results/aidev_sample_scaleup.jsonl",
                             "results/aidev_sample_v2.jsonl",
                             "results/aidev_sample.jsonl"])
    ap.add_argument("--out-dir", default="outputs/tse_gap_closure/data")
    ap.add_argument("--cache-dir", default="outputs/tse_gap_closure/data/pr_files_cache")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-fetch", type=int, default=None,
                    help="cap the number of GitHub diff fetches (debug)")
    args = ap.parse_args()
    collect(args.candidates, args.embedded, args.out_dir, args.cache_dir,
            args.workers, args.max_fetch)


if __name__ == "__main__":
    main()

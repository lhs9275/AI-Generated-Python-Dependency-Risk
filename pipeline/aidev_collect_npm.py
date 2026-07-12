#!/usr/bin/env python3
"""GitHub API로 agent-authored npm (JS/TS) PR 수집 — npm 일반화 연구용 collector.

PyPI collector (aidev_collect.py)의 npm 포팅. 사람 평가 없음
([[asg-no-human-evaluation]]): 수집은 raw agent-authored package.json
dependency-change PR + 매니페스트 patch만 모으고, risk 라벨링은 자동
F1/F2/F3 단계(npm registry / semver resolution / OSV-npm)가 별도로 처리한다.

PyPI 버전과 동일한 sampling frame, 차이는 두 가지뿐:
  - language:JavaScript + language:TypeScript (각각 검색)
  - dependency manifest = package.json (선언 파일; 자동생성 lockfile은
    잡음·대용량이라 제외해 신호를 깨끗하게 유지)

aidev_collect 의 검증된 helper(gh_request rate-limit 백오프, get_pr_files,
AGENT_QUERIES)를 재사용하며 PyPI collector 는 건드리지 않는다(제출본 의존).

저장 최소화: PR 당 package.json patch + 슬림 메타데이터만 저장. 전체 파일
목록/내용은 저장하지 않는다(개수만 n_files_total 로 기록).

사용:
  export GITHUB_TOKEN=...
  python -m pipeline.aidev_collect_npm --out results/aidev_npm_sample.jsonl --target 1200
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import sys
sys.path.insert(0, os.path.dirname(__file__))
from aidev_collect import gh_request, get_pr_files, AGENT_QUERIES, API  # noqa: E402

NPM_MANIFESTS = {"package.json"}
LANGS = ["JavaScript", "TypeScript"]


def search_prs_npm(agent: str, qualifier: str, token: str,
                   per_page: int = 30, max_pages: int = 3) -> list:
    """agent author/co-author 로 merged JS+TS PR 검색 (두 언어 합산)."""
    out = []
    for lang in LANGS:
        for page in range(1, max_pages + 1):
            q = f"is:pr is:merged language:{lang} {qualifier}"
            url = f"{API}/search/issues?q={q.replace(' ', '+')}&per_page={per_page}&page={page}"
            print(f"  [{agent}] {lang} page {page}: {q}")
            res = gh_request(url, token)
            if not isinstance(res, dict) or not res.get("items"):
                break
            for item in res["items"]:
                pr = (item.get("pull_request") or {}).get("url")
                if not pr:
                    continue
                out.append({
                    "agent": agent,
                    "lang": lang,
                    "html_url": item["html_url"],
                    "title": item["title"],
                    "created_at": item["created_at"],
                    "repository_url": item["repository_url"],
                    "user": item["user"]["login"],
                    "pr_api_url": pr,
                })
            time.sleep(2)
    return out


def npm_dep_change(files: list[dict]) -> dict:
    """package.json 변경 검출. 매니페스트 patch만 보존(저장 최소)."""
    changed = []
    for f in files:
        name = (f.get("filename") or "").rsplit("/", 1)[-1]
        if name in NPM_MANIFESTS:
            changed.append({
                "path": f["filename"],
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                # full patch retained (PyPI collector와 동일 이유: truncation이
                # 큰 매니페스트 diff에서 의존성 라인을 조용히 누락시켜 위험을
                # 과소집계함). package.json patch는 작아 저장 부담 미미.
                "patch": (f.get("patch") or ""),
            })
    return {"has_change": bool(changed), "manifests": changed}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--target", type=int, default=1200,
                   help="dependency-changing PR 목표 수 (PyPI 연구 1168 PR 와 비교)")
    p.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    p.add_argument("--token-file", default=os.path.expanduser("~/.gh_token"))
    p.add_argument("--max-pages", type=int, default=3)
    args = p.parse_args()

    if not args.token and Path(args.token_file).exists():
        args.token = Path(args.token_file).read_text().strip()
        print(f"[+] token from {args.token_file} (len={len(args.token)})")
    if not args.token:
        print("[!] GITHUB_TOKEN not set — unauthenticated 60 req/hour, search 10/min")

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # 1단계: agent 별 후보 수집 (쿼리별 즉시 체크포인트 — 환경의 백그라운드
    # job reaper 대비, 재실행 시 완료 쿼리 skip)
    cand_path = args.out.with_suffix(".candidates.jsonl")
    done_path = args.out.with_suffix(".done.json")
    candidates, seen_urls = [], set()
    if cand_path.exists():
        for line in cand_path.read_text().splitlines():
            if line.strip():
                pr = json.loads(line)
                if pr["html_url"] not in seen_urls:
                    seen_urls.add(pr["html_url"]); candidates.append(pr)
    done_queries = set(json.loads(done_path.read_text())) if done_path.exists() else set()
    print(f"[resume] {len(candidates)} candidates, {len(done_queries)} queries done")

    for agent, qualifier in AGENT_QUERIES:
        qid = f"{agent}|{qualifier}"
        if qid in done_queries:
            continue
        prs = search_prs_npm(agent, qualifier, args.token, per_page=30, max_pages=args.max_pages)
        print(f"  [{agent}] found {len(prs)} candidate PRs (JS+TS)")
        with cand_path.open("a", encoding="utf-8") as fh:
            for pr in prs:
                if pr["html_url"] in seen_urls:
                    continue
                seen_urls.add(pr["html_url"]); candidates.append(pr)
                fh.write(json.dumps(pr, ensure_ascii=False) + "\n")
        done_queries.add(qid)
        done_path.write_text(json.dumps(sorted(done_queries), ensure_ascii=False))
        time.sleep(2)

    print(f"\nTotal unique candidates: {len(candidates)}")

    # 2단계: package.json 변경 필터 (증분 저장 + resume)
    filtered_urls, n_filtered = set(), 0
    checked_path = args.out.with_suffix(".checked.json")
    checked = set(json.loads(checked_path.read_text())) if checked_path.exists() else set()
    if args.out.exists():
        for line in args.out.read_text().splitlines():
            if line.strip():
                filtered_urls.add(json.loads(line)["html_url"]); n_filtered += 1
    print(f"[resume] phase2: {n_filtered} kept, {len(checked)} checked")

    for i, pr in enumerate(candidates):
        if n_filtered >= args.target:
            break
        if pr["html_url"] in checked or pr["html_url"] in filtered_urls:
            continue
        print(f"[{i+1}/{len(candidates)}] checking {pr['html_url']}")
        files = get_pr_files(pr["pr_api_url"], args.token)
        dep = npm_dep_change(files)
        checked.add(pr["html_url"])
        if dep["has_change"]:
            pr["dep_changes"] = dep["manifests"]
            pr["n_files_total"] = len(files)  # 개수만 — 파일 내용 저장 안 함
            n_filtered += 1
            with args.out.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(pr, ensure_ascii=False) + "\n")
            print(f"  ✓ package.json-changing [{n_filtered}/{args.target}]")
        if len(checked) % 20 == 0:
            checked_path.write_text(json.dumps(sorted(checked), ensure_ascii=False))
        time.sleep(1)
    checked_path.write_text(json.dumps(sorted(checked), ensure_ascii=False))

    filtered = []
    if args.out.exists():
        filtered = [json.loads(l) for l in args.out.read_text().splitlines() if l.strip()]
    print(f"\nSaved {len(filtered)} package.json-changing agent PRs → {args.out}")

    by_agent: dict[str, int] = {}
    for pr in filtered:
        by_agent[pr["agent"]] = by_agent.get(pr["agent"], 0) + 1
    print(f"By agent: {by_agent}")


if __name__ == "__main__":
    main()

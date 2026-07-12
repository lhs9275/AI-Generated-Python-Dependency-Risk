"""Repo-stratified downsample of the naturalistic corpus to a target PR count.

Rationale: the full mined corpus (1{,}1xx PRs) is larger than needed for the
paired analysis. We downsample to ~500 PRs WITHOUT any new fetching:

  * every PR carrying a primary risk (P1/P2/P3) is kept in full (전수 보존), so the
    primary-risk evidence is never reduced;
  * the remaining (independently safe) PRs are sub-sampled repo-stratified with a
    fixed seed (42), maximizing repository diversity in the kept safe set.

Outputs the reduced ``dependency_change_patches.jsonl`` (the full file is backed
up as ``*.full.jsonl``) plus a ``downsample_log.json``. Evidence/labels are keyed
by change_id, so downstream steps simply restrict to the retained changes.
"""

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path

PRIMARY = {"P1_NONEXISTENT_PACKAGE", "P2_INVALID_VERSION_SPEC", "P3_DIRECT_KNOWN_VULNERABILITY"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--patches", default="outputs/tse_gap_closure/data/dependency_change_patches.jsonl")
    ap.add_argument("--labels", default="outputs/tse_gap_closure/data/independent_labels.csv")
    ap.add_argument("--target", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    patches = [json.loads(l) for l in Path(args.patches).read_text().splitlines() if l.strip()]
    prim = {}
    with open(args.labels, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            prim[r["change_id"]] = r["label_primary"]

    # group changes by PR
    by_pr = defaultdict(list)
    for r in patches:
        by_pr[r["pr_id"]].append(r)
    pr_repo = {pr: rows[0].get("repo_full_name") for pr, rows in by_pr.items()}
    risk_prs = {pr for pr, rows in by_pr.items()
                if any(prim.get(r["change_id"]) in PRIMARY for r in rows)}
    safe_prs = [pr for pr in by_pr if pr not in risk_prs]

    # repo-stratified round-robin sample of safe PRs to fill the budget
    budget = max(0, args.target - len(risk_prs))
    rng = random.Random(args.seed)
    by_repo = defaultdict(list)
    for pr in safe_prs:
        by_repo[pr_repo.get(pr)].append(pr)
    repos = list(by_repo)
    rng.shuffle(repos)
    for repo in repos:
        rng.shuffle(by_repo[repo])
    picked_safe = []
    i = 0
    while len(picked_safe) < budget and any(by_repo[r] for r in repos):
        repo = repos[i % len(repos)]
        if by_repo[repo]:
            picked_safe.append(by_repo[repo].pop())
        i += 1

    keep_prs = risk_prs | set(picked_safe)
    kept = [r for r in patches if r["pr_id"] in keep_prs]

    full_backup = Path(args.patches).with_suffix(".full.jsonl")
    if not full_backup.exists():
        full_backup.write_text(Path(args.patches).read_text())
    with open(args.patches, "w", encoding="utf-8") as fh:
        for r in kept:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    log = {
        "seed": args.seed, "target_prs": args.target,
        "n_prs_full": len(by_pr), "n_changes_full": len(patches),
        "n_risk_prs_kept_all": len(risk_prs),
        "n_safe_prs_sampled": len(picked_safe),
        "n_prs_kept": len(keep_prs),
        "n_changes_kept": len(kept),
        "n_repos_kept": len({pr_repo[pr] for pr in keep_prs}),
        "primary_changes_kept": sum(1 for r in kept if prim.get(r["change_id"]) in PRIMARY),
        "primary_changes_full": sum(1 for r in patches if prim.get(r["change_id"]) in PRIMARY),
        "backup": str(full_backup),
    }
    Path("outputs/tse_gap_closure/data/downsample_log.json").write_text(json.dumps(log, indent=2))
    print(json.dumps(log, indent=2))
    assert log["primary_changes_kept"] == log["primary_changes_full"], "primary risk not fully preserved!"
    print("OK primary risk fully preserved.")


if __name__ == "__main__":
    main()

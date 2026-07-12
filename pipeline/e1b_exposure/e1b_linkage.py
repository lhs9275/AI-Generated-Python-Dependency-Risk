#!/usr/bin/env python3
"""e1b_linkage -- link PR-time risk + gate decision + real-world outcome. (E1b step 3/3)

Joins five sources on change_id / pr_id and produces the "Real-World Exposure
Linkage" analysis that answers the disjoint-generator objection: on the SAME
population where we measured prevalence (deployed-agent PRs), do the gate's BLOCK
decisions correspond to PRs that actually MERGED and whose risk actually
MATERIALIZED?

Sources:
  --patches   per-change records (change_id -> pr_id, created_at)
  --labels    labeler_A output (change_id -> label_primary; P1/P2/P3 = primary)
  --gate      run_gate_ladder output guard_outputs.jsonl (change_id -> decisions{B3})
  --outcomes  e1b_collect_merge output  (pr_id  -> merged, repo_stars)
  --realized  e1b_materialize_risk output (change_id -> realized, lead-time)

Outputs: linkage_summary.json, linkage_table.csv, linkage_table.tex

CAUSAL SCOPE (state this in the paper): observational. The gate did not act on
these PRs, so this is NOT a merge-rate treatment effect. It quantifies preventable
real-world EXPOSURE -- risky changes that merged and materialized and that the
gate's frozen-evidence BLOCK set would have flagged -- on the prevalence
population. It bridges prevalence and the gate without claiming causal mitigation.

Pure stdlib.
"""
import argparse
import csv
import datetime as dt
import json
import math
import os
import sys

PRIMARY = {"P1_NONEXISTENT_PACKAGE", "P2_INVALID_VERSION_SPEC", "P3_DIRECT_KNOWN_VULNERABILITY"}


def log(m):
    print(m, file=sys.stderr, flush=True)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (p, (c - h) / d, (c + h) / d)


def load_jsonl(path):
    """Yield dicts from .jsonl or .csv (auto-detect)."""
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                yield row
    else:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)


def b3_key(decisions):
    if not isinstance(decisions, dict):
        return None
    for k in decisions:
        if k == "B3" or k.endswith("B3") or k.lower() == "b3":
            return k
    return None


def parse_dt(s):
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patches", default="results/tse_gap_closure/data/dependency_change_patches.jsonl")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--gate", required=True, help="guard_outputs.jsonl from run_gate_ladder")
    ap.add_argument("--outcomes", required=True, help="pr_outcomes.jsonl from e1b_collect_merge")
    ap.add_argument("--realized", required=True, help="risk_realized.jsonl from e1b_materialize_risk")
    ap.add_argument("--out-dir", default="results/e1b_exposure")
    ap.add_argument("--star-tier", type=int, default=5, help="repo stars >= this = non-toy tier")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    # joins
    pr_of, created = {}, {}
    for p in load_jsonl(args.patches):
        cid = p.get("change_id")
        if cid:
            pr_of[cid] = p.get("pr_id")
            created[cid] = p.get("created_at")
    label = {o["change_id"]: o.get("label_primary", "NONE") for o in load_jsonl(args.labels)}
    gate = {}
    for o in load_jsonl(args.gate):
        k = b3_key(o.get("decisions"))
        if k:
            gate[o["change_id"]] = o["decisions"][k]
    merged, stars = {}, {}
    for o in load_jsonl(args.outcomes):
        merged[o["pr_id"]] = o.get("merged")
        stars[o["pr_id"]] = o.get("repo_stars")
    realized, ltype, disclosure = {}, {}, {}
    for o in load_jsonl(args.realized):
        realized[o["change_id"]] = o.get("realized")
        ltype[o["change_id"]] = o.get("risk_type")
        disclosure[o["change_id"]] = o.get("earliest_disclosure")

    # PR-level risk flag (a PR is risky if >=1 primary-risky change)
    pr_risky = {}
    for cid, lp in label.items():
        pid = pr_of.get(cid)
        if pid is not None:
            pr_risky[pid] = pr_risky.get(pid, False) or (lp in PRIMARY)

    # ---- merge rate: risky vs safe PRs (coverage-limited to PRs with known outcome)
    def rate(pred):
        ks = [pid for pid, rk in pr_risky.items() if rk == pred and merged.get(pid) is not None]
        k = sum(1 for pid in ks if merged.get(pid))
        return k, len(ks), wilson(k, len(ks))

    r_k, r_n, r_w = rate(True)
    s_k, s_n, s_w = rate(False)

    # ---- change-level analysis over primary-risky changes with full join
    risky = [cid for cid, lp in label.items() if lp in PRIMARY]
    rows = []
    for cid in risky:
        pid = pr_of.get(cid)
        rows.append({
            "change_id": cid, "pr_id": pid, "risk_type": ltype.get(cid),
            "b3": gate.get(cid), "merged": merged.get(pid),
            "realized": realized.get(cid), "stars": stars.get(pid),
        })
    full = [r for r in rows if r["b3"] is not None and r["merged"] is not None and r["realized"] is not None]

    # 3-way crosstab counts
    cube = {}
    for r in full:
        key = (r["b3"], bool(r["merged"]), bool(r["realized"]))
        cube[key] = cube.get(key, 0) + 1

    # headline: unmitigated preventable exposure
    block_merge_real = sum(1 for r in full if r["b3"] == "BLOCK" and r["merged"] and r["realized"])
    merged_real = sum(1 for r in full if r["merged"] and r["realized"])
    total_changes = sum(1 for _ in load_jsonl(args.patches))

    # P3 lead-time (days between PR and earliest advisory disclosure)
    leads = []
    for cid in risky:
        if ltype.get(cid) == "P3" and disclosure.get(cid):
            d0, d1 = parse_dt(created.get(cid)), parse_dt(disclosure.get(cid))
            if d0 and d1:
                leads.append((d1 - d0).days)
    silent = sum(1 for x in leads if x > 0)   # disclosed AFTER the PR = PR-time-uncatchable

    # repo tier
    nontoy = sum(1 for r in full if r["b3"] == "BLOCK" and r["merged"] and r["realized"]
                 and (r["stars"] or 0) >= args.star_tier)

    summary = {
        "join_coverage": {
            "primary_risky_changes": len(risky),
            "fully_joined": len(full),
            "missing_gate": sum(1 for r in rows if r["b3"] is None),
            "missing_merge": sum(1 for r in rows if r["merged"] is None),
            "missing_realized": sum(1 for r in rows if r["realized"] is None),
        },
        "merge_rate": {
            "risky_pr": {"merged": r_k, "n": r_n, "rate": r_w[0], "ci": [r_w[1], r_w[2]]},
            "safe_pr": {"merged": s_k, "n": s_n, "rate": s_w[0], "ci": [s_w[1], s_w[2]]},
        },
        "exposure": {
            "block_AND_merged_AND_realized": block_merge_real,
            "rate_over_fully_joined": wilson(block_merge_real, len(full))[0],
            "rate_over_all_changes": (block_merge_real / total_changes) if total_changes else None,
            "merged_AND_realized_any_decision": merged_real,
            "block_share_of_merged_realized": (block_merge_real / merged_real) if merged_real else None,
            "nontoy_repo_subset": nontoy,
        },
        "p3_lead_time_days": {
            "n": len(leads),
            "silent_disclosed_after_pr": silent,
            "median": (sorted(leads)[len(leads) // 2] if leads else None),
            "min": (min(leads) if leads else None), "max": (max(leads) if leads else None),
        },
        "crosstab_b3_merged_realized": {f"{a}|merged={b}|realized={c}": n
                                        for (a, b, c), n in sorted(cube.items())},
        "_caveat": "Observational exposure linkage, not a causal merge-rate effect of the gate.",
    }

    with open(os.path.join(args.out_dir, "linkage_summary.json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)

    # csv: per-change joined rows (audit trail)
    with open(os.path.join(args.out_dir, "linkage_rows.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["change_id", "pr_id", "risk_type", "b3", "merged", "realized", "stars"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # latex table (paper-ready): B3 decision x outcome, over fully-joined primary-risky changes
    decs = ["BLOCK", "WARN", "PASS"]
    def cnt(d, mg, rl):
        return sum(1 for r in full if r["b3"] == d and bool(r["merged"]) == mg and bool(r["realized"]) == rl)
    lines = [
        r"\begin{table}[t]\centering",
        r"\caption{Real-world exposure linkage on the naturalistic prevalence population "
        r"(primary-risky changes with full join, $n=%d$). Observational: the gate did not "
        r"act on these PRs. ``Exposed'' = merged \emph{and} risk materialized.}" % len(full),
        r"\label{tab:exposure}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"B3 decision & Exposed (merged\&real) & Merged, not real & Not merged \\",
        r"\midrule",
    ]
    for d in decs:
        exposed = cnt(d, True, True)
        merged_notreal = cnt(d, True, False)
        notmerged = sum(1 for r in full if r["b3"] == d and not r["merged"])
        lines.append(r"%s & %d & %d & %d \\" % (d, exposed, merged_notreal, notmerged))
    lines += [
        r"\midrule",
        r"\multicolumn{4}{l}{\footnotesize Preventable exposure (B3=BLOCK $\wedge$ merged $\wedge$ materialized): "
        r"\textbf{%d} changes" % block_merge_real,
        r"(%.2f\%% of all %d changes); BLOCK is %.0f\%% of all merged-\&-materialized risk.}\\" % (
            (100.0 * block_merge_real / total_changes) if total_changes else 0.0, total_changes,
            (100.0 * block_merge_real / merged_real) if merged_real else 0.0),
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    with open(os.path.join(args.out_dir, "linkage_table.tex"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    log("=== E1b linkage ===")
    log(f"  primary-risky changes: {len(risky)}  fully-joined: {len(full)}")
    log(f"  risky-PR merge rate: {r_w[0]:.3f} [{r_w[1]:.3f},{r_w[2]:.3f}] (n={r_n})")
    log(f"  safe-PR  merge rate: {s_w[0]:.3f} [{s_w[1]:.3f},{s_w[2]:.3f}] (n={s_n})")
    log(f"  preventable exposure (BLOCK&merged&materialized): {block_merge_real}")
    log(f"  P3 silent (advisory disclosed after PR): {silent}/{len(leads)}")
    log(f"  wrote -> {args.out_dir}/linkage_summary.json, linkage_table.tex, linkage_rows.csv")


if __name__ == "__main__":
    main()

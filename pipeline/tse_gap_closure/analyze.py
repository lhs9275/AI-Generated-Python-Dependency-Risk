"""Metrics + paired statistics for the naturalistic gate-ladder evaluation.

Joins the guard-independent labels (independent_labels.csv) with the guard gate
decisions (guard_outputs.jsonl) on ``change_id`` and answers EV-RQ2/3/4:

  * per-variant accept/block, primary-risky acceptance, safe-block (false
    positive), and missed-primary (false negative) rates;
  * the minimal-gate ladder (B0 -> S1 -> S1S2 -> S1S2S3 -> +license -> B3) with
    each rung's marginal block contribution;
  * the scanner-scope mismatch (what an off-the-shelf vulnerability scanner
    accepts that a direct-public-evidence gate blocks);
  * paired tests (McNemar exact + conditional OR), paired rate differences with
    Wilson and repo-clustered bootstrap 95% CIs, for B0/B1/S1S2S3/B3 contrasts.

Analysis population = dependency *introductions/changes* (change_type in
{add, version_change}); removals cannot introduce a risk and are reported
separately. The decision unit is one dependency change; repository is the
clustering unit for the clustered bootstrap.
"""

import argparse
import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from statsmodels.stats.proportion import proportion_confint

from pipeline.stats_paired import _mcnemar_exact, _odds_ratio_ci

PRIMARY = {"P1_NONEXISTENT_PACKAGE", "P2_INVALID_VERSION_SPEC",
           "P3_DIRECT_KNOWN_VULNERABILITY"}
LADDER = ["B0_no_gate", "B1_scanner_fail_open", "B1b_scanner_fail_closed",
          "S1_existence", "S1S2_version", "S1S2S3_direct_evidence",
          "S1S2S3_plus_license", "B3_full_guard"]
PAIRS = [("B0_no_gate", "S1S2S3_direct_evidence"),
         ("B1_scanner_fail_open", "S1S2S3_direct_evidence"),
         ("S1S2S3_direct_evidence", "B3_full_guard"),
         ("B0_no_gate", "B3_full_guard")]


def _wilson(k, n):
    if n == 0:
        return (None, None)
    lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
    return round(lo, 4), round(hi, 4)


def _blocked(dec):
    return dec == "BLOCK"


def cluster_bootstrap_diff(rows, repo_of, stat, n_boot=2000, seed=42):
    """Repo-clustered bootstrap 95% CI for a paired statistic over rows.

    Resamples repositories (clusters) with replacement; ``stat(sample_rows)``
    returns the scalar (e.g. a paired rate difference) recomputed per resample.
    """
    by_repo = defaultdict(list)
    for r in rows:
        by_repo[repo_of(r)].append(r)
    repos = list(by_repo)
    if not repos:
        return None, None, None
    rng = random.Random(seed)
    point = stat(rows)
    boots = []
    for _ in range(n_boot):
        sample = []
        for _ in range(len(repos)):
            sample.extend(by_repo[repos[rng.randrange(len(repos))]])
        v = stat(sample)
        if v is not None:
            boots.append(v)
    if not boots:
        return point, None, None
    boots.sort()
    lo = boots[int(len(boots) * 0.025)]
    hi = boots[int(len(boots) * 0.975)]
    return point, round(lo, 4), round(hi, 4)


def load(labels_csv, guard_jsonl):
    labels = {}
    with open(labels_csv, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            labels[row["change_id"]] = row
    guard = {}
    for ln in Path(guard_jsonl).read_text().splitlines():
        if ln.strip():
            r = json.loads(ln)
            guard[r["change_id"]] = r
    # join (only changes that have both a label and a guard decision)
    joined = []
    for cid, g in guard.items():
        lab = labels.get(cid)
        if not lab:
            continue
        joined.append({**g, "label_primary": (lab.get("label_primary") or "NONE").strip() or "NONE",
                       "label_secondary": (lab.get("label_secondary") or "NONE").strip() or "NONE",
                       "label_confidence": lab.get("label_confidence")})
    return joined


def load_full_labels(labels_csv):
    """All labeled introductions/changes (PREVALENCE basis -- the full mined corpus,
    not the downsampled gate-analysis set), with a derived source-tool field."""
    out = []
    with open(labels_csv, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("change_type") not in ("add", "version_change"):
                continue
            r["agent"] = (r.get("tool_evidence") or "").split(":")[-1] or "unknown"
            r["label_primary"] = (r.get("label_primary") or "NONE").strip() or "NONE"
            r["label_secondary"] = (r.get("label_secondary") or "NONE").strip() or "NONE"
            out.append(r)
    return out


def summary_table(rows):
    """Per-variant counts/rates over the analysis population."""
    n = len(rows)
    risky = [r for r in rows if r["label_primary"] in PRIMARY]
    safe = [r for r in rows if r["label_primary"] == "NONE"]
    sec = [r for r in rows if r["label_secondary"] not in ("NONE", "")]
    out = []
    for v in LADDER:
        decs = [r["decisions"].get(v) for r in rows]
        blocked = sum(1 for d in decs if _blocked(d))
        warned = sum(1 for d in decs if d == "WARN")
        pr_acc = sum(1 for r in risky if not _blocked(r["decisions"].get(v)))
        pr_blk = len(risky) - pr_acc
        sb = sum(1 for r in safe if _blocked(r["decisions"].get(v)))
        sec_warn = sum(1 for r in sec if r["decisions"].get(v) == "WARN")
        out.append({
            "variant": v,
            "n": n,
            "accepted": n - blocked,
            "blocked": blocked,
            "warned": warned,
            "n_primary_risky": len(risky),
            "primary_risky_accepted": pr_acc,
            "primary_risky_acceptance_rate": round(pr_acc / len(risky), 4) if risky else None,
            "primary_risk_block_rate": round(pr_blk / len(risky), 4) if risky else None,
            "n_safe": len(safe),
            "safe_block_count": sb,
            "safe_block_rate": round(sb / len(safe), 4) if safe else None,
            "false_positive_count": sb,
            "false_negative_count": pr_acc,
            "n_secondary": len(sec),
            "secondary_warning_rate": round(sec_warn / len(sec), 4) if sec else None,
        })
    return out, risky, safe, sec


def minimal_gate(rows):
    """Marginal block contribution of each ladder rung (guard rungs only)."""
    rungs = ["B0_no_gate", "S1_existence", "S1S2_version",
             "S1S2S3_direct_evidence", "S1S2S3_plus_license", "B3_full_guard"]
    out = []
    prev_blocked = set()
    for v in rungs:
        blk = {r["change_id"] for r in rows if _blocked(r["decisions"].get(v))}
        marginal = blk - prev_blocked
        out.append({"rung": v, "cumulative_blocked": len(blk),
                    "marginal_new_blocks": len(marginal),
                    "marginal_frac_of_total": round(len(marginal) / max(1, len(rows)), 4)})
        prev_blocked = blk
    return out


def scope_mismatch(rows):
    """What the off-the-shelf scanner accepts that the direct-evidence gate blocks.

    Counts dependency changes by (scanner decision, S1S2S3 decision), split by
    independent primary-risk label, to expose the scanner's structural blind spot.
    """
    out = []
    for prim in ["P1_NONEXISTENT_PACKAGE", "P2_INVALID_VERSION_SPEC",
                 "P3_DIRECT_KNOWN_VULNERABILITY", "NONE"]:
        sub = [r for r in rows if r["label_primary"] == prim]
        if not sub:
            continue
        sc_block = sum(1 for r in sub if _blocked(r["decisions"].get("B1_scanner_fail_open")))
        gate_block = sum(1 for r in sub if _blocked(r["decisions"].get("S1S2S3_direct_evidence")))
        scanner_miss_gate_catch = sum(
            1 for r in sub
            if not _blocked(r["decisions"].get("B1_scanner_fail_open"))
            and _blocked(r["decisions"].get("S1S2S3_direct_evidence")))
        out.append({"primary_label": prim, "n": len(sub),
                    "scanner_blocked": sc_block, "direct_gate_blocked": gate_block,
                    "scanner_missed_but_gate_caught": scanner_miss_gate_catch})
    return out


def prevalence_by_source(rows):
    by = defaultdict(lambda: Counter())
    for r in rows:
        agent = r.get("agent") or "unknown"
        by[agent]["n"] += 1
        if r["label_primary"] in PRIMARY:
            by[agent]["primary_risky"] += 1
            by[agent][r["label_primary"]] += 1
        if r["label_secondary"] not in ("NONE", ""):
            by[agent]["secondary"] += 1
    out = []
    for agent, c in sorted(by.items()):
        d = {"source_tool": agent, "n_changes": c["n"], "n_primary_risky": c["primary_risky"],
             "P1": c["P1_NONEXISTENT_PACKAGE"], "P2": c["P2_INVALID_VERSION_SPEC"],
             "P3": c["P3_DIRECT_KNOWN_VULNERABILITY"], "n_secondary": c["secondary"]}
        out.append(d)
    return out


def paired(rows, left, right):
    """McNemar on 'blocked' + paired rate diffs (safe-block, primary-risky-accept)."""
    b = c = both1 = both0 = 0
    for r in rows:
        lv = _blocked(r["decisions"].get(left))
        rv = _blocked(r["decisions"].get(right))
        if lv and not rv:
            b += 1
        elif not lv and rv:
            c += 1
        elif lv and rv:
            both1 += 1
        else:
            both0 += 1
    p = _mcnemar_exact(b, c)
    odds = _odds_ratio_ci(both1, b, c, both0)

    safe = [r for r in rows if r["label_primary"] == "NONE"]
    risky = [r for r in rows if r["label_primary"] in PRIMARY]

    def sb_diff(rs):
        s = [r for r in rs if r["label_primary"] == "NONE"]
        if not s:
            return None
        l = sum(1 for r in s if _blocked(r["decisions"].get(left))) / len(s)
        rr = sum(1 for r in s if _blocked(r["decisions"].get(right))) / len(s)
        return rr - l  # right minus left

    def pra_diff(rs):
        s = [r for r in rs if r["label_primary"] in PRIMARY]
        if not s:
            return None
        l = sum(1 for r in s if not _blocked(r["decisions"].get(left))) / len(s)
        rr = sum(1 for r in s if not _blocked(r["decisions"].get(right))) / len(s)
        return rr - l

    repo_of = lambda r: r.get("repo") or "?"
    sb_pt, sb_lo, sb_hi = cluster_bootstrap_diff(rows, repo_of, sb_diff)
    pra_pt, pra_lo, pra_hi = cluster_bootstrap_diff(rows, repo_of, pra_diff)
    return {
        "left": left, "right": right, "n_pairs": b + c + both1 + both0,
        "left_blocked": both1 + b, "right_blocked": both1 + c,
        "discordant_left_only": b, "discordant_right_only": c,
        "mcnemar_p": round(p, 6), "odds_ratio": odds,
        "safe_block_rate_diff_right_minus_left": sb_pt,
        "safe_block_rate_diff_ci": [sb_lo, sb_hi],
        "primary_risky_accept_diff_right_minus_left": pra_pt,
        "primary_risky_accept_diff_ci": [pra_lo, pra_hi],
        "n_safe": len(safe), "n_primary_risky": len(risky),
    }


def fp_analysis(rows):
    """Safe (non-primary) dependency changes blocked by B3, typed by firing stage."""
    out = []
    for r in rows:
        if r["label_primary"] != "NONE":
            continue
        if not _blocked(r["decisions"].get("B3_full_guard")):
            continue
        fired = r.get("fired_stages", {}).get("B3", [])
        out.append({"change_id": r["change_id"], "repo": r.get("repo"), "agent": r.get("agent"),
                    "package": r.get("package_name"), "pinned_version": r.get("pinned_version"),
                    "secondary_label": r["label_secondary"], "fired_stages_B3": "|".join(fired)})
    return out


def fn_analysis(rows):
    """Primary-risky changes accepted (not blocked) by each ladder variant."""
    out = []
    for r in rows:
        if r["label_primary"] not in PRIMARY:
            continue
        accepted_by = [v for v in LADDER if not _blocked(r["decisions"].get(v))]
        out.append({"change_id": r["change_id"], "repo": r.get("repo"), "agent": r.get("agent"),
                    "package": r.get("package_name"), "pinned_version": r.get("pinned_version"),
                    "primary_label": r["label_primary"],
                    "accepted_by_variants": "|".join(accepted_by)})
    return out


def _wcsv(path, rows):
    if not rows:
        Path(path).write_text("")
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", default="outputs/tse_gap_closure/data/independent_labels.csv")
    ap.add_argument("--guard", default="outputs/tse_gap_closure/data/guard_outputs.jsonl")
    ap.add_argument("--out-dir", default="outputs/tse_gap_closure/analysis")
    args = ap.parse_args()
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    joined_all = load(args.labels, args.guard)
    # GATE-analysis population (downsampled corpus): introductions/changes only.
    pop = [r for r in joined_all if r["change_type"] in ("add", "version_change")]
    removes = [r for r in joined_all if r["change_type"] == "remove"]

    # PREVALENCE basis: the FULL mined corpus labels (downsampling retains all
    # primary risk but uniformly sub-samples safe changes, so risky/total in `pop`
    # is enriched; the unbiased naturalistic prevalence is computed here from full).
    full_pop = load_full_labels(args.labels)
    full_risky = [r for r in full_pop if r["label_primary"] in PRIMARY]
    prevalence_full = {
        "n_changes_full": len(full_pop),
        "n_primary_risky_full": len(full_risky),
        "primary_prevalence_full": round(len(full_risky) / len(full_pop), 4) if full_pop else None,
        "primary_label_counts_full": dict(Counter(r["label_primary"] for r in full_pop)),
        "n_prs_full": len({r.get("pr_id") for r in full_pop}),
        "n_repos_full": len({r.get("repo") for r in full_pop}),
    }
    (out / "prevalence_full.json").write_text(json.dumps(prevalence_full, indent=2, ensure_ascii=False))

    summ, risky, safe, sec = summary_table(pop)
    _wcsv(out / "naturalistic_validation_summary.csv", summ)
    _wcsv(out / "prevalence_by_source.csv", prevalence_by_source(full_pop))
    _wcsv(out / "minimal_gate_comparison.csv", minimal_gate(pop))
    _wcsv(out / "scanner_scope_mismatch.csv", scope_mismatch(pop))
    _wcsv(out / "false_positive_analysis.csv", fp_analysis(pop))
    _wcsv(out / "false_negative_analysis.csv", fn_analysis(pop))

    # risky-acceptance-by-gate with Wilson CIs
    rab = []
    for v in LADDER:
        acc = sum(1 for r in risky if not _blocked(r["decisions"].get(v)))
        lo, hi = _wilson(acc, len(risky))
        rab.append({"variant": v, "n_primary_risky": len(risky),
                    "primary_risky_accepted": acc,
                    "acceptance_rate": round(acc / len(risky), 4) if risky else None,
                    "wilson_ci_low": lo, "wilson_ci_high": hi})
    _wcsv(out / "risky_acceptance_by_gate.csv", rab)

    stats = {p[0] + "_vs_" + p[1]: paired(pop, *p) for p in PAIRS}
    meta = {
        "gate_analysis_sample": "repo-stratified 500-PR downsample (seed 42); all "
                                "primary-risk PRs retained, safe PRs sub-sampled. "
                                "Within-stratum acceptance/safe-block rates unbiased.",
        "n_joined_changes": len(joined_all),
        "n_analysis_population_add_or_versionchange": len(pop),
        "n_removes_excluded": len(removes),
        "n_primary_risky": len(risky),
        "n_safe": len(safe),
        "n_secondary_labeled": len(sec),
        "primary_label_counts": dict(Counter(r["label_primary"] for r in pop)),
        "secondary_label_counts": dict(Counter(r["label_secondary"] for r in pop)),
        "n_repos": len({r.get("repo") for r in pop}),
        "n_prs": len({r.get("pr_id") for r in pop}),
        "prevalence_full_corpus": prevalence_full,
        "paired_stats": stats,
    }
    (out / "paired_stats.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

    print(f"analysis population: {len(pop)} dependency changes "
          f"({meta['n_prs']} PRs, {meta['n_repos']} repos)")
    print(f"primary-risky: {len(risky)}  safe: {len(safe)}  secondary: {len(sec)}")
    print(f"primary label counts: {meta['primary_label_counts']}")
    print("per-variant block / safe-block / primary-risky-accept:")
    for s in summ:
        print(f"  {s['variant']:26s} blk={s['blocked']:5d} "
              f"safe_blk_rate={s['safe_block_rate']} "
              f"primary_risky_acc_rate={s['primary_risky_acceptance_rate']}")
    print(f"wrote analysis CSVs + paired_stats.json -> {out}")


if __name__ == "__main__":
    main()

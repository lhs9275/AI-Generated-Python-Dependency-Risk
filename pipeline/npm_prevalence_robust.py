#!/usr/bin/env python3
"""npm prevalence robustness battery -- the PyPI sensitivity analyses, ported.

Reads the per-change detail (results/npm_risk_labels.jsonl) + the slim registry/
OSV caches and reports the SAME robustness axes the PyPI study reports, so the
cross-ecosystem generality claim carries identical rigor:

  (1) gate impact     -- F3 with vs without the PR-time advisory-disclosure gate
                         (shows the live-OSV inflation the gate removes).
  (2) temporal grade  -- strict-at-PR-time vs temporally-ambiguous, mirroring the
                         PyPI 3.7% -> 3.1% floor split (ambiguous = bare-* present-
                         time 404s + forward-pins whose version published just
                         after the PR).
  (3) tool-mix reweight - leave-one-tool-out + equal-tool-weight (PyPI 3.6-5.5%).
  (4) repo clustering  - collapse to one any-risk flag per repo (de-inflates a
                         single monorepo contributing many identical changes).

No network, no GPU; pure recompute from archived artifacts.
Writes results/npm_prevalence_robust.json.
"""
from __future__ import annotations

import collections
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from npm_evidence import _affects                                    # noqa: E402
from npm_semver import UNPARSEABLE                                    # noqa: E402

HERE = Path(__file__).resolve().parent.parent
RES = HERE / "results"


def main():
    rows = [json.loads(l) for l in (RES / "npm_risk_labels.jsonl").read_text().splitlines() if l.strip()]
    reg = json.loads((RES / "npm_reg_cache.json").read_text())
    osv = json.loads((RES / "npm_osv_cache.json").read_text())
    n = len(rows)
    risky = [r for r in rows if r["label"] in ("F1", "F2", "F3")]

    # (1) gate impact: F3 count with vs without the published<=PR gate
    gated_f3 = sum(1 for r in rows if r["label"] == "F3")
    live_f3 = 0
    for r in rows:
        ver = r.get("resolved")
        advs = osv.get(r["name"])
        if not advs or not ver or ver == UNPARSEABLE:
            continue
        if any(_affects(a, ver) for a in advs):
            live_f3 += 1

    # (2) temporal grade. strict = F3 (advisory disclosed before PR, unambiguous).
    #     ambiguous = F1 bare-* present-time 404s + F2 forward-pins (version exists
    #     now -> published after the PR).
    f1 = [r for r in rows if r["label"] == "F1"]
    f2 = [r for r in rows if r["label"] == "F2"]
    f3 = [r for r in rows if r["label"] == "F3"]
    f2_forward = 0
    for r in f2:
        slim = reg.get(r["name"]) or {}
        pin = r["spec"].lstrip("v=").strip()
        if slim.get("exists") and pin in (slim.get("versions") or {}):
            f2_forward += 1
    strict_risky = len(f3)                     # unambiguous PR-time grade
    strict_rate = round(strict_risky / max(n, 1), 4)
    full_rate = round(len(risky) / max(n, 1), 4)

    # (3) tool-mix reweight (change-level rate per tool, then re-aggregate)
    by_tool = collections.defaultdict(lambda: {"n": 0, "risky": 0})
    for r in rows:
        t = r.get("agent") or "unknown"
        by_tool[t]["n"] += 1
        by_tool[t]["risky"] += 1 if r["label"] in ("F1", "F2", "F3") else 0
    tool_rates = {t: round(d["risky"] / max(d["n"], 1), 4) for t, d in by_tool.items()}
    # leave-one-out (drop one tool, pooled over the rest)
    loo = {}
    for drop in by_tool:
        num = sum(d["risky"] for t, d in by_tool.items() if t != drop)
        den = sum(d["n"] for t, d in by_tool.items() if t != drop)
        loo[f"drop_{drop}"] = round(num / max(den, 1), 4)
    # equal-tool-weight (mean of per-tool rates); and over tools with n>=100
    eq_all = round(sum(tool_rates.values()) / max(len(tool_rates), 1), 4)
    big = [t for t, d in by_tool.items() if d["n"] >= 100]
    eq_big = round(sum(tool_rates[t] for t in big) / max(len(big), 1), 4) if big else None

    # (4) repo clustering: one any-risk flag per repo
    repos = collections.defaultdict(lambda: {"changes": 0, "risky": False})
    for r in rows:
        repos[r["repo"]]["changes"] += 1
        repos[r["repo"]]["risky"] = repos[r["repo"]]["risky"] or (r["label"] in ("F1", "F2", "F3"))
    repos_any = sum(1 for v in repos.values() if v["risky"])
    f2_repos = len({r["repo"] for r in f2})

    out = {
        "n_changes": n,
        "full_prevalence": full_rate,
        "family_counts": {"F1": len(f1), "F2": len(f2), "F3": len(f3),
                          "NONE": n - len(risky)},
        "gate_impact": {
            "F3_pr_time_gated": gated_f3,
            "F3_live_osv_no_gate": live_f3,
            "F3_removed_by_gate": live_f3 - gated_f3,
            "note": "PR-time advisory-disclosure gate removes post-PR advisories the live OSV would over-count",
        },
        "temporal_grade": {
            "strict_at_pr_time_rate": strict_rate,
            "strict_risky": strict_risky,
            "full_rate": full_rate,
            "ambiguous_F1_present_time_404": len(f1),
            "ambiguous_F2_forward_pins": f2_forward,
            "note": "mirrors PyPI 3.7%->3.1% strict floor; strict=F3, ambiguous=bare-* 404 + forward-pins",
        },
        "tool_mix": {
            "per_tool_rate": tool_rates,
            "per_tool_n": {t: d["n"] for t, d in by_tool.items()},
            "leave_one_out": loo,
            "equal_tool_weight_all": eq_all,
            "equal_tool_weight_n_ge_100": eq_big,
        },
        "repo_clustering": {
            "n_repos": len(repos),
            "repos_any_risk": repos_any,
            "repo_level_rate": round(repos_any / max(len(repos), 1), 4),
            "F2_repos": f2_repos,
            "note": f"F2's {len(f2)} changes span {f2_repos} repo(s) -> per-repo de-inflates monorepo platform-package clusters",
        },
    }
    (RES / "npm_prevalence_robust.json").write_text(json.dumps(out, indent=2))

    print("=== npm prevalence robustness (PyPI-matched) ===")
    print(f"full change-level prevalence: {full_rate:.2%} ({len(risky)}/{n})")
    print(f"  F1 {len(f1)}  F2 {len(f2)}  F3 {len(f3)}")
    g = out["gate_impact"]
    print(f"gate impact (F3): PR-time-gated {g['F3_pr_time_gated']} vs live-OSV {g['F3_live_osv_no_gate']} "
          f"(gate removed {g['F3_removed_by_gate']})")
    t = out["temporal_grade"]
    print(f"temporal grade: strict-at-PR-time {t['strict_at_pr_time_rate']:.2%} (F3 only) .. full {t['full_rate']:.2%}; "
          f"ambiguous = {t['ambiguous_F1_present_time_404']} bare-* 404 + {t['ambiguous_F2_forward_pins']} forward-pin")
    m = out["tool_mix"]
    print(f"tool-mix: per-tool {m['per_tool_rate']}")
    print(f"  leave-one-out range {min(m['leave_one_out'].values()):.2%}..{max(m['leave_one_out'].values()):.2%}; "
          f"equal-weight all {m['equal_tool_weight_all']:.2%}, n>=100 {m['equal_tool_weight_n_ge_100']}")
    rc = out["repo_clustering"]
    print(f"repo clustering: {rc['repos_any_risk']}/{rc['n_repos']} repos any-risk = {rc['repo_level_rate']:.2%}; "
          f"F2 in {rc['F2_repos']} repo(s)")
    print(f"-> results/npm_prevalence_robust.json")


if __name__ == "__main__":
    main()

"""
Naturalistic B3 residual decomposition + operational cost (manuscript §4.6).

Reproduces the revised residual claims:
  - 117 primary-risky accepted by B3 = 105 WARN-surfaced (sub-threshold P3)
    + 12 silent PASS (10 P3 with no matching advisory in the frozen PR-time OSV
    snapshot; 2 P2 version-boundary).
  - PR-time-expressible matching failure = 0.
  - WARN->merge: of the unique PRs carrying residual primary risk, what fraction
    were actually merged (operational cost of the WARN policy knob).

Usage:
    python -m pipeline.tse_gap_closure.residual_operational_cost
"""

import csv
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parents[2] / "outputs" / "tse_gap_closure"
PRS = Path(__file__).resolve().parents[2] / "results" / "tse_gap_closure_github_prs.jsonl"


def _decisions(raw):
    return eval(raw) if isinstance(raw, str) else raw


def main() -> None:
    # 117 residual primary-risky accepted by full guard
    resid = {}
    fn = BASE / "analysis" / "false_negative_analysis.csv"
    for r in csv.DictReader(fn.open()):
        if "B3_full_guard" in r["accepted_by_variants"]:
            resid[r["change_id"]] = r["primary_label"]

    # B3 decision per residual change (WARN-surfaced vs silent PASS)
    dec, fired = {}, {}
    for line in (BASE / "data" / "guard_outputs.jsonl").open():
        d = json.loads(line)
        de = _decisions(d["decisions"])
        dec[d["change_id"]] = de.get("B3_full_guard") or de.get("B3")
        fired[d["change_id"]] = _decisions(d["fired_stages"]).get("B3")

    surf = Counter((lab[:2], dec.get(cid, "?")) for cid, lab in resid.items())

    # WARN->merge among PRs carrying residual primary risk
    merged = {}
    for line in PRS.open():
        d = json.loads(line)
        m = re.match(r"https://github.com/(.+?)/pull/(\d+)", d.get("html_url", ""))
        if m:
            merged[f"{m.group(1)}#{m.group(2)}"] = bool(d.get("merged_at"))
    resid_prs = {cid.split("::")[0] for cid in resid}
    known = [p for p in resid_prs if p in merged]
    n_merged = sum(merged[p] for p in known)

    print(f"residual primary-risky accepted by B3 : {len(resid)}")
    for k, v in sorted(surf.items()):
        print(f"  {k[0]} {k[1]:5s}: {v}")
    warn = sum(v for (l, d), v in surf.items() if d == "WARN")
    pas = sum(v for (l, d), v in surf.items() if d == "PASS")
    print(f"  WARN-surfaced={warn}  silent-PASS={pas}")
    print(f"residual-risk PRs: {len(resid_prs)} ({len(known)} with merge state)")
    print(f"  merged: {n_merged}/{len(known)} = {n_merged/len(known)*100:.1f}%")


if __name__ == "__main__":
    main()

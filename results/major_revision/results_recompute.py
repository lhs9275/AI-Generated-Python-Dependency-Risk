#!/usr/bin/env python3
"""Deterministic recompute of ALL Results-section derived numbers from the
corrected labels. Reproduce the original 328 baseline first (validates the
parse), then apply changed_rows_final.csv (55 FP->NONE, 6 FN->P3) and emit the
corrected prevalence, per-tool, PR-level, repo-level, merged-subset, tool-mix
sensitivity, and Wilson 95% CIs. No number is hand-entered."""
import csv, math, json, os

BASE = os.path.dirname(os.path.abspath(__file__))
LBL = os.path.join(BASE, "..", "tse_gap_closure", "data", "independent_labels.csv")
CHG = os.path.join(BASE, "changed_rows_final.csv")

def wilson(k, n):
    if n == 0: return (0.0, 0.0)
    z = 1.959963984540054
    p = k / n
    d = 1 + z*z/n
    c = (p + z*z/(2*n)) / d
    h = (z/d) * math.sqrt(p*(1-p)/n + z*z/(4*n*n))
    return (100*(c-h), 100*(c+h))

def pct(k, n): return 100.0*k/n if n else 0.0

# --- load labels ---
rows = []
with open(LBL, newline="") as f:
    for r in csv.DictReader(f):
        rows.append(r)

def is_primary(lbl): return lbl.startswith(("P1_","P2_","P3_"))
def pcls(lbl):
    if lbl.startswith("P1_"): return "P1"
    if lbl.startswith("P2_"): return "P2"
    if lbl.startswith("P3_"): return "P3"
    return "NONE"

# prevalence universe = add + version_change (removals excluded)
uni = [r for r in rows if r["change_type"] in ("add","version_change")]
DENOM = len(uni)

# --- BASELINE (original labels) ---
base_primary = [r for r in uni if is_primary(r["label_primary"])]
base_counts = {"P1":0,"P2":0,"P3":0}
for r in base_primary: base_counts[pcls(r["label_primary"])] += 1
base_total = len(base_primary)

# --- load corrections ---
fp_ids, fn_ids = set(), set()
with open(CHG, newline="") as f:
    for r in csv.DictReader(f):
        if r["new_label"] == "NONE": fp_ids.add(r["change_id"])
        else: fn_ids.add(r["change_id"])

# corrected label per change
def corrected_label(r):
    cid = r["change_id"]
    if cid in fp_ids: return "NONE"
    if cid in fn_ids: return "P3_DIRECT_KNOWN_VULNERABILITY"
    return r["label_primary"]

corr_primary = [r for r in uni if is_primary(corrected_label(r))]
corr_counts = {"P1":0,"P2":0,"P3":0}
for r in corr_primary: corr_counts[pcls(corrected_label(r))] += 1
corr_total = len(corr_primary)

def tool(r): return r["tool_evidence"].split(":")[-1]

# per-tool corrected
tools = {}
for r in uni:
    t = tool(r)
    tools.setdefault(t, [0,0])
    tools[t][1] += 1
    if is_primary(corrected_label(r)): tools[t][0] += 1

# PR-level / repo-level (>=1 corrected primary)
pr_has, pr_all = set(), set()
repo_has, repo_all = set(), set()
for r in uni:
    pr_all.add(r["pr_id"]); repo_all.add(r["repo"])
    if is_primary(corrected_label(r)):
        pr_has.add(r["pr_id"]); repo_has.add(r["repo"])

# merged subset (merged_at non-empty)
merged = [r for r in uni if r["merged_at"].strip()]
merged_primary = [r for r in merged if is_primary(corrected_label(r))]
merged_p1 = [r for r in merged if corrected_label(r).startswith("P1_")]
p1_all = [r for r in uni if corrected_label(r).startswith("P1_")]

# tool-mix sensitivity
tool_rates = {t:(k/n) for t,(k,n) in tools.items() if n>=100}
tool_rates_all = {t:(k/n) for t,(k,n) in tools.items() if n>0}
# leave-one-tool-out pooled
loo = {}
for t in tools:
    k = corr_total - tools[t][0]
    n = DENOM - tools[t][1]
    loo[t] = 100*k/n
equal5 = 100*sum(tool_rates.values())/len(tool_rates)
equalall = 100*sum(tool_rates_all.values())/len(tool_rates_all)

out = {
 "DENOM_add_vc": DENOM,
 "baseline_total": base_total, "baseline_counts": base_counts,
 "corrected_total": corr_total, "corrected_counts": corr_counts,
 "corrected_prevalence_pct": round(pct(corr_total,DENOM),4),
 "corrected_prevalence_wilson": [round(x,3) for x in wilson(corr_total,DENOM)],
 "removals_only_floor_pct": round(pct(base_total-len(fp_ids),DENOM),4),
 "p3_dominance_pct": round(100*corr_counts["P3"]/corr_total,2),
 "per_tool": {t:{"k":k,"n":n,"pct":round(pct(k,n),2),
                 "wilson":[round(x,2) for x in wilson(k,n)]}
              for t,(k,n) in sorted(tools.items(), key=lambda x:-x[1][1])},
 "pr_level": {"k":len(pr_has),"n":len(pr_all),"pct":round(pct(len(pr_has),len(pr_all)),2),
              "wilson":[round(x,2) for x in wilson(len(pr_has),len(pr_all))]},
 "repo_level": {"k":len(repo_has),"n":len(repo_all),"pct":round(pct(len(repo_has),len(repo_all)),2),
                "wilson":[round(x,2) for x in wilson(len(repo_has),len(repo_all))]},
 "merged": {"k":len(merged_primary),"n":len(merged),"pct":round(pct(len(merged_primary),len(merged)),2),
            "wilson":[round(x,2) for x in wilson(len(merged_primary),len(merged))]},
 "p1_all": {"k":len(p1_all),"n":DENOM,"pct":round(pct(len(p1_all),DENOM),3),
            "wilson":[round(x,3) for x in wilson(len(p1_all),DENOM)]},
 "p1_merged": {"k":len(merged_p1),"n":len(merged),"pct":round(pct(len(merged_p1),len(merged)),3)},
 "tool_mix": {"leave_one_out_pct":{t:round(v,2) for t,v in sorted(loo.items())},
              "loo_range":[round(min(loo.values()),2),round(max(loo.values()),2)],
              "equal_tool_5_n100_pct":round(equal5,2),
              "equal_tool_all_pct":round(equalall,2)},
 "fp_ids_n":len(fp_ids),"fn_ids_n":len(fn_ids),
}
print(json.dumps(out, indent=1))

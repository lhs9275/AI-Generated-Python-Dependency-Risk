#!/usr/bin/env python3
"""e1a_aggregate -- RiskyAcc-Core (F1+F2+F3) under agentic generation, B0 vs B3. (E1a step 3/3)

Walks the swept run results, computes the PAIRED gate effect (RiskyAcc-Core under
B0 vs B3) per (model, condition) pooled across seeds, with Wilson CIs, and writes
a paper-ready comparison against the single-pass numbers. The headline question:
does the single-pass 15.8--35.8% -> 0.8--3.3% reduction HOLD under agentic
generation by the same/overlapping tool population? If yes, the causal mitigation
result is no longer confined to the disjoint single-pass open-weight setting.

Scoring: this expects each run dir to contain a SCORED manifest (per-task records
with the B0/B3 guard decision). If only the raw generation manifest is present,
re-run pipeline/agentic/score_agentic_outputs.py first (or pass --score to let
this invoke it). The reader is defensive about field names; if it cannot find the
per-mode risky-accept signal it prints the fields actually present so the schema
adapter can be fixed.

Pure stdlib (+ optional subprocess for --score).
"""
import argparse
import csv
import json
import math
import os
import subprocess
import sys

CORE = {"F1", "F2", "F3"}
SCORER = "pipeline/agentic/score_agentic_outputs.py"


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


def first(d, *names, default=None):
    for n in names:
        if isinstance(d, dict) and n in d and d[n] is not None:
            return d[n]
    return default


def family_of(rec):
    f = first(rec, "family", "risk_family", "task_family")
    if f:
        return str(f)[:2].upper()
    tid = str(first(rec, "task_id", "task", "change_id", default=""))
    for fam in ("F1", "F2", "F3", "F4", "F5", "F6"):
        if fam in tid:
            return fam
    return None


def decision_pass(rec, mode):
    """True if the gate `mode` ACCEPTED (PASS/WARN) the patch."""
    s = first(rec, mode + "_score", mode + "_decision", mode)
    if s is None:
        return None
    return str(s).upper() in ("PASS", "WARN", "ACCEPT", "ACCEPTED")


def patch_risky(rec):
    """Whether the generated patch actually carries the family risk (oracle)."""
    v = first(rec, "patch_risky", "is_risky_patch", "oracle_risky", "risky_patch")
    if v is not None:
        return bool(v)
    # fallback: under B0 (no gate) a risky-accept means the patch was risky
    ra = first(rec, "RiskyAcc_B0", "B0_RiskyAcc")
    if ra is not None:
        return bool(ra)
    ra = first(rec, "RiskyAcc")
    if ra is not None and decision_pass(rec, "B0") is not False:
        return bool(ra)
    return None


def load_records(run_dir):
    """Yield per-task scored records from a run dir (manifest.json list or per-task jsons)."""
    man = os.path.join(run_dir, "manifest.json")
    if os.path.exists(man):
        try:
            d = json.load(open(man))
        except Exception:
            d = None
        if isinstance(d, list):
            yield from d
            return
        if isinstance(d, dict):
            for key in ("tasks", "results", "runs", "records"):
                if isinstance(d.get(key), list):
                    yield from d[key]
                    return
    for fn in sorted(os.listdir(run_dir)):
        if fn.endswith(".json") and fn != "manifest.json":
            try:
                r = json.load(open(os.path.join(run_dir, fn)))
                if isinstance(r, dict):
                    yield r
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", default="results/agentic_e1a/sweep.jsonl")
    ap.add_argument("--single-pass", default="", help="CSV with model,RiskyAcc_Core_B0,RiskyAcc_Core_B3 (optional)")
    ap.add_argument("--out-dir", default="results/agentic_e1a")
    ap.add_argument("--score", action="store_true", help="invoke score_agentic_outputs.py on unscored runs")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    sweep = [json.loads(l) for l in open(args.sweep) if l.strip()]
    sp = {}
    if args.single_pass and os.path.exists(args.single_pass):
        for row in csv.DictReader(open(args.single_pass)):
            sp[row.get("model") or row.get("model_tag")] = row

    # accumulate: (model_tag, condition) -> {B0: [risky_accepts], B3: [...]} over core tasks
    agg = {}
    diag_fields = set()
    seen_records = parse_fail = 0
    for row in sweep:
        rd = row["results_dir"]
        if not os.path.isdir(rd):
            continue
        if args.score and not os.path.exists(os.path.join(rd, ".scored")):
            subprocess.call([sys.executable, SCORER, os.path.join(rd, "manifest.json"),
                             "--task-dir", "bench"])
            open(os.path.join(rd, ".scored"), "w").write("ok\n")
        key = (row["model_tag"], row["condition"])
        a = agg.setdefault(key, {"B0_risky": 0, "B3_risky": 0, "n_core": 0})
        for rec in load_records(rd):
            diag_fields.update(k for k in rec.keys()) if isinstance(rec, dict) else None
            fam = family_of(rec)
            if fam not in CORE:
                continue
            pr = patch_risky(rec)
            b0 = decision_pass(rec, "B0")
            b3 = decision_pass(rec, "B3")
            if pr is None or b3 is None:
                parse_fail += 1
                continue
            a["n_core"] += 1
            # RiskyAcc = patch risky AND gate accepted
            if pr and (b0 is None or b0):
                a["B0_risky"] += 1
            if pr and b3:
                a["B3_risky"] += 1
            seen_records += 1

    if seen_records == 0:
        log("ERROR: no scorable core records found.")
        log("fields present in records: " + ", ".join(sorted(diag_fields)) or "(none)")
        log("Fix: run scoring (--score) or adapt field names in e1a_aggregate.py "
            "(family / B0_score / B3_score / patch_risky).")
        sys.exit(3)

    # write outputs
    rows_out = []
    for (mt, cond), a in sorted(agg.items()):
        n = a["n_core"]
        b0p, b0lo, b0hi = wilson(a["B0_risky"], n)
        b3p, b3lo, b3hi = wilson(a["B3_risky"], n)
        rows_out.append({"model_tag": mt, "condition": cond, "n_core": n,
                         "RiskyAcc_Core_B0": round(b0p, 4), "B0_ci": [round(b0lo, 4), round(b0hi, 4)],
                         "RiskyAcc_Core_B3": round(b3p, 4), "B3_ci": [round(b3lo, 4), round(b3hi, 4)],
                         "delta_pp": round(100 * (b0p - b3p), 2),
                         "single_pass": sp.get(mt)})

    json.dump(rows_out, open(os.path.join(args.out_dir, "e1a_summary.json"), "w"),
              indent=2, ensure_ascii=False)
    with open(os.path.join(args.out_dir, "e1a_riskyacc_core.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model_tag", "condition", "n_core", "RiskyAcc_Core_B0", "RiskyAcc_Core_B3", "delta_pp"])
        for r in rows_out:
            w.writerow([r["model_tag"], r["condition"], r["n_core"],
                        r["RiskyAcc_Core_B0"], r["RiskyAcc_Core_B3"], r["delta_pp"]])

    tex = [r"\begin{table}[t]\centering",
           r"\caption{RiskyAcc-Core (F1+F2+F3) under \emph{agentic} generation, paired B0 vs B3. "
           r"Closes the single-pass-vs-agentic generation-mode gap of the controlled intervention.}",
           r"\label{tab:e1a}", r"\begin{tabular}{llrrrr}", r"\toprule",
           r"Model & Cond & $n$ & B0 & B3 & $\Delta$pp \\", r"\midrule"]
    for r in rows_out:
        tex.append(r"%s & %s & %d & %.1f\%% & %.1f\%% & %.1f \\" % (
            r["model_tag"].replace("_", r"\_"), r["condition"].split("_")[-1],
            r["n_core"], 100 * r["RiskyAcc_Core_B0"], 100 * r["RiskyAcc_Core_B3"], r["delta_pp"]))
    tex += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    open(os.path.join(args.out_dir, "e1a_table.tex"), "w").write("\n".join(tex) + "\n")

    log("=== E1a aggregate ===")
    for r in rows_out:
        log(f"  {r['model_tag']:28s} {r['condition']:30s} n={r['n_core']:3d} "
            f"B0={100*r['RiskyAcc_Core_B0']:.1f}% B3={100*r['RiskyAcc_Core_B3']:.1f}% d={r['delta_pp']}pp")
    if parse_fail:
        log(f"  ({parse_fail} records skipped for missing fields)")
    log(f"  wrote -> {args.out_dir}/e1a_summary.json, e1a_riskyacc_core.csv, e1a_table.tex")


if __name__ == "__main__":
    main()

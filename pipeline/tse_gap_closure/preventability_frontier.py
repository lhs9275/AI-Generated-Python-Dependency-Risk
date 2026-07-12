#!/usr/bin/env python3
"""PR-time public-evidence *preventability frontier* (re-analysis of existing data).

Holds the B3 full-guard DETECTION fixed and varies only the WARN-enforcement
policy, characterizing the trade-off between enforcement recall (primary risk
actually blocked) and safe-block cost. Reuses the same independent labels and
guard decisions as Table VI (no new data, no network, no GPU).

Policies (WARN = detected-but-below-HIGH severity):
  block_only          : WARN -> accept (current paper default)
  warn_requires_approval : WARN -> human-gated (enforcement bounded, observational)
  warn_as_block       : WARN -> block (maximal enforcement)

Run:
  python -m pipeline.tse_gap_closure.preventability_frontier \
      --labels results/tse_gap_closure/data/independent_labels.csv \
      --guard  results/tse_gap_closure/data/guard_outputs.jsonl \
      --out-dir results/tse_gap_closure/analysis
"""
import argparse
import csv
import json
from pathlib import Path

PRIMARY = {"P1_NONEXISTENT_PACKAGE", "P2_INVALID_VERSION_SPEC",
           "P3_DIRECT_KNOWN_VULNERABILITY"}
GRADE = {"P1_NONEXISTENT_PACKAGE": "P1", "P2_INVALID_VERSION_SPEC": "P2",
         "P3_DIRECT_KNOWN_VULNERABILITY": "P3"}


def _wilson(k, n):
    try:
        from statsmodels.stats.proportion import proportion_confint
    except Exception:
        return (None, None)
    if n == 0:
        return (None, None)
    lo, hi = proportion_confint(k, n, alpha=0.05, method="wilson")
    return round(lo, 4), round(hi, 4)


def load(labels_csv, guard_jsonl):
    labels = {}
    with open(labels_csv, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            labels[r["change_id"]] = (
                (r.get("label_primary") or "NONE").strip() or "NONE")
    rows = []
    for ln in Path(guard_jsonl).read_text().splitlines():
        if not ln.strip():
            continue
        g = json.loads(ln)
        cid = g["change_id"]
        if cid not in labels:
            continue
        # Match Table VI's gate-analysis population: introductions/version changes
        # only (the downsampled 4,948-change set), excluding 'remove' changes.
        if g.get("change_type") not in ("add", "version_change"):
            continue
        rows.append({"primary": labels[cid],
                     "b3": g["decisions"].get("B3_full_guard")})
    return rows


def frontier(rows):
    risky = [r for r in rows if r["primary"] in PRIMARY]
    safe = [r for r in rows if r["primary"] == "NONE"]
    n_p, n_s = len(risky), len(safe)

    def part(pop):
        return (sum(1 for r in pop if r["b3"] == "BLOCK"),
                sum(1 for r in pop if r["b3"] == "WARN"),
                sum(1 for r in pop if r["b3"] not in ("BLOCK", "WARN")))

    pB, pW, pP = part(risky)   # primary: BLOCK / WARN / silent-PASS
    sB, sW, sP = part(safe)    # safe:    BLOCK / WARN / PASS

    # detection recall (any surfacing) is policy-invariant
    det_recall = (pB + pW) / n_p
    silent_floor = pP / n_p    # irreducible PR-time public-evidence miss

    policies = []
    # block_only: enforce = BLOCK; WARN accepted
    policies.append(("block_only", pB, sB))
    # warn_as_block: enforce = BLOCK + WARN
    policies.append(("warn_as_block", pB + pW, sB + sW))

    out = []
    for name, enf_blocked_primary, safe_blocked in policies:
        out.append({
            "policy": name,
            "n_primary": n_p,
            "enforcement_recall": round(enf_blocked_primary / n_p, 4),
            "enforcement_recall_ci": _wilson(enf_blocked_primary, n_p),
            "primary_accepted": n_p - enf_blocked_primary,
            "primary_accepted_rate": round((n_p - enf_blocked_primary) / n_p, 4),
            "detection_recall": round(det_recall, 4),
            "safe_block_count": safe_blocked,
            "safe_block_rate": round(safe_blocked / n_s, 4),
            "safe_block_ci": _wilson(safe_blocked, n_s),
        })

    # warn_requires_approval sits between the two corners: detection recall is
    # complete-down-to-floor (same surfacing as warn_as_block) but realized
    # enforcement depends on the approval discipline, which is unobserved here.
    approval = {
        "policy": "warn_requires_approval",
        "n_primary": n_p,
        "enforcement_recall_lower": round(pB / n_p, 4),       # if every WARN approved
        "enforcement_recall_upper": round((pB + pW) / n_p, 4),  # if every WARN rejected
        "detection_recall": round(det_recall, 4),
        "note": ("realized enforcement between block_only and warn_as_block; "
                 "depends on unobserved human approval rate (observational)"),
    }

    grades = {}
    for g in ("P1", "P2", "P3"):
        gp = [r for r in risky if GRADE.get(r["primary"]) == g]
        b, w, p = part(gp)
        grades[g] = {"n": len(gp), "block": b, "warn": w, "silent_pass": p}

    return {
        "primary_partition": {"block": pB, "warn": pW, "silent_pass": pP, "n": n_p},
        "safe_partition": {"block": sB, "warn": sW, "pass": sP, "n": n_s},
        "detection_recall": round(det_recall, 4),
        "silent_miss_floor": round(silent_floor, 4),
        "by_grade": grades,
        "policies": out,
        "warn_requires_approval": approval,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default="results/tse_gap_closure/data/independent_labels.csv")
    ap.add_argument("--guard", default="results/tse_gap_closure/data/guard_outputs.jsonl")
    ap.add_argument("--out-dir", default="results/tse_gap_closure/analysis")
    a = ap.parse_args()

    rows = load(a.labels, a.guard)
    res = frontier(rows)

    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "preventability_frontier.json").write_text(json.dumps(res, indent=2))
    with open(out_dir / "preventability_frontier.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["policy", "enforcement_recall", "primary_accepted_rate",
                    "detection_recall", "safe_block_rate"])
        for p in res["policies"]:
            w.writerow([p["policy"], p["enforcement_recall"],
                        p["primary_accepted_rate"], p["detection_recall"],
                        p["safe_block_rate"]])
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()

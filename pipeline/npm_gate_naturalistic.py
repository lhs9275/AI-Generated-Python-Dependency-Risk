#!/usr/bin/env python3
"""Apply the npm core gate (S1+S2+S3) to the naturalistic 1,284-change corpus.

This is the npm analogue of the PyPI naturalistic gate validation. It reuses the
already-computed F1/F2/F3/NONE labels (results/npm_risk_labels.jsonl): because each
label IS the most-severe-wins outcome of the same public-evidence stages, the gate's
per-stage decision is a direct function of the label --
    F1 -> S1 BLOCK, F2 -> S2 BLOCK, F3 -> S3 (BLOCK if a covering advisory is
    >= HIGH else WARN), NONE -> PASS.
Only F3 needs the advisory severity, fetched from OSV for the F3 package set.

IMPORTANT (honesty): on THIS corpus the gate's stages and the labels derive from the
same public evidence, so the clean-change false-block rate is ~0 by construction. That
is *why* the independent external recall corpus (npm_external_recall.py) exists -- it is
the non-circular specificity/recall test. The naturalistic numbers here report block vs.
detection recall on the 62 risky changes and confirm zero false-block on the 1,222 clean
changes, mirroring the PyPI naturalistic validation.

Output: results/npm_gate_naturalistic.json
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import npm_gate  # noqa: E402
from npm_gate import _RANK, _MODE_STAGES  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "external_realrisk"))
from metrics import compute_recall_matrix  # noqa: E402

MIN_SEV = "HIGH"
_FAM = {"F1": "S1", "F2": "S2", "F3": "S3"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def _f3_severity(name, osv_ids, osv_sev_cache):
    """Max qualitative severity among `osv_ids` for npm `name` (cached)."""
    advs = osv_sev_cache.get(name)
    if advs is None:
        advs = osv_sev_cache[name] = npm_gate.fetch_osv_sev(name)
        import time
        time.sleep(0.06)
    if not advs:
        return None
    idset = set(osv_ids)
    worst = 0
    for a in advs:
        if a.get("id") in idset:
            worst = max(worst, _RANK.get(a.get("severity") or "", 0))
    return worst


def stage_decisions(label, sev_rank):
    """Per-stage PASS/WARN/BLOCK from a label (+ F3 severity rank)."""
    s = {"S1": "PASS", "S2": "PASS", "S3": "PASS", "S3_audit": "PASS"}
    if label == "F1":
        s["S1"] = "BLOCK"
    elif label == "F2":
        s["S2"] = "BLOCK"
    elif label == "F3":
        s["S3"] = "BLOCK" if (sev_rank or 0) >= _RANK[MIN_SEV] else "WARN"
        s["S3_audit"] = "BLOCK"
    return s


def mode_decisions(stage):
    out = {}
    for mode, enabled in _MODE_STAGES.items():
        decs = [stage[x] for x in enabled]
        out[mode] = "BLOCK" if "BLOCK" in decs else ("WARN" if "WARN" in decs else "PASS")
    return out


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    results = os.path.join(here, "results")
    sev_path = os.path.join(results, "npm_gate_osv_sev_cache.json")
    osv_sev_cache = json.load(open(sev_path)) if os.path.exists(sev_path) else {}

    rows = []
    f3_block = f3_warn = 0
    sev_dist = {}
    with open(os.path.join(results, "npm_risk_labels.jsonl")) as f:
        for line in f:
            rec = json.loads(line)
            label = rec.get("label", "NONE")
            sev_rank = None
            if label == "F3":
                sev_rank = _f3_severity(rec["name"], rec.get("osv_ids") or [], osv_sev_cache)
                if (sev_rank or 0) >= _RANK[MIN_SEV]:
                    f3_block += 1
                else:
                    f3_warn += 1
                band = {0: "unknown", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}[sev_rank or 0]
                sev_dist[band] = sev_dist.get(band, 0) + 1
            stage = stage_decisions(label, sev_rank)
            rows.append({
                "record_id": rec.get("pr", "") + "::" + rec["name"],
                "label": "normal" if label == "NONE" else "risky",
                "family": _FAM.get(label, "NONE"),
                "primary": label in _FAM,
                "decisions": mode_decisions(stage),
            })

    matrix = compute_recall_matrix(rows)
    core = matrix["modes"]["S1_S2_S3"]
    base = matrix["modes"]["npm_audit"]

    out = {
        "min_blocked_severity": MIN_SEV,
        "n_changes": len(rows),
        "n_risky": core["n_risky"],
        "n_clean": core["n_normal"],
        "f3_severity_split": {"block_ge_high": f3_block, "warn_below_high": f3_warn,
                              "severity_band": sev_dist},
        "headline_mode": "S1_S2_S3",
        "matrix": matrix,
        "circularity_note": "gate stages and F1/F2/F3 labels derive from the same public "
                            "evidence on this corpus, so clean-change false-block is ~0 by "
                            "construction; the non-circular recall/specificity test is the "
                            "independent external corpus (npm_external_recall.json).",
    }
    json.dump(out, open(os.path.join(results, "npm_gate_naturalistic.json"), "w"), indent=2)
    json.dump(osv_sev_cache, open(sev_path, "w"))

    log(f"naturalistic gate on {len(rows)} changes  risky={core['n_risky']} clean={core['n_normal']}")
    log(f"  CORE S1_S2_S3 block-recall={core['recall']:.3f} CI{core['recall_ci']} "
        f"detection={core['detection_recall']:.3f} false-block={core['false_block_rate']}")
    log(f"  npm_audit base block-recall={base['recall']:.3f} (misses S1+S2) "
        f"false-block={base['false_block_rate']}")
    log(f"  F3 severity split: BLOCK(>=HIGH)={f3_block} WARN(<HIGH)={f3_warn} dist={sev_dist}")
    log(f"  per-family core block: " +
        ", ".join(f"{k}={v['blocked']}/{v['n']}" for k, v in core["family_recall"].items()))


if __name__ == "__main__":
    main()

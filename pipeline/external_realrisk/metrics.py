"""Recall / precision / family matrix + Wilson CI for the external-realrisk corpus.

Pure functions over a list of per-record evaluation rows::

    {"record_id", "label": "risky"|"normal", "family": "S1"|...|"NONE",
     "primary": bool, "decisions": {mode: "PASS"|"WARN"|"BLOCK"}}

A risky record is *caught* by a mode iff its decision is BLOCK (WARN/PASS = accepted),
matching the seeded-recall convention. Primary recall counts only S1/S2/S3 families;
secondary families (S5 license, F6 unnecessary) are reported separately.
"""

import math

_Z = 1.959963984540054  # 95%


def wilson_ci(k: int, n: int, z: float = _Z):
    """Wilson score interval for k successes in n trials. (None, None) if n == 0."""
    if n == 0:
        return (None, None)
    phat = k / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    return (round(max(0.0, center - half), 6), round(min(1.0, center + half), 6))


def _ratio(num, den):
    return (num / den) if den else None


def compute_recall_matrix(rows: list[dict]) -> dict:
    """Per-mode recall/precision/false-block/family-recall + confusion + CIs."""
    modes = []
    for r in rows:
        for m in r.get("decisions", {}):
            if m not in modes:
                modes.append(m)

    risky = [r for r in rows if r["label"] == "risky"]
    normal = [r for r in rows if r["label"] == "normal"]
    primary = [r for r in risky if r.get("primary")]
    families = []
    for r in risky:
        if r["family"] not in families:
            families.append(r["family"])

    def blocked(r, m):
        return r["decisions"].get(m) == "BLOCK"

    def detected(r, m):
        return r["decisions"].get(m) in ("BLOCK", "WARN")

    out = {}
    for m in modes:
        tp = sum(1 for r in risky if blocked(r, m))
        fn = len(risky) - tp
        fp = sum(1 for r in normal if blocked(r, m))
        tn = len(normal) - fp
        det = sum(1 for r in risky if detected(r, m))
        prim_tp = sum(1 for r in primary if blocked(r, m))
        fam_recall = {}
        for fam in families:
            fam_rows = [r for r in risky if r["family"] == fam]
            fb = sum(1 for r in fam_rows if blocked(r, m))
            fam_recall[fam] = {"n": len(fam_rows), "blocked": fb,
                               "recall": _ratio(fb, len(fam_rows))}
        out[m] = {
            "n": len(rows),
            "n_risky": len(risky),
            "n_normal": len(normal),
            "recall": _ratio(tp, len(risky)),
            "recall_ci": list(wilson_ci(tp, len(risky))),
            "detection_recall": _ratio(det, len(risky)),
            "detection_recall_ci": list(wilson_ci(det, len(risky))),
            "primary_recall": _ratio(prim_tp, len(primary)),
            "primary_recall_ci": list(wilson_ci(prim_tp, len(primary))),
            "precision": _ratio(tp, tp + fp),
            "false_block_rate": _ratio(fp, len(normal)),
            "negative_pass_rate": _ratio(tn, len(normal)),
            "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
            "family_recall": fam_recall,
        }
    return {"modes": out,
            "n_primary_risky": len(primary),
            "families": families}

#!/usr/bin/env python3
"""positive_class_agreement -- positive-class labeler agreement (κ robustness).

The headline Cohen κ=0.90 is computed over a label space that is 96.8% NONE, so a
reviewer can object that it is inflated by trivial agreement on the majority-negative
class. This recomputes agreement RESTRICTED to the positive (risky) classes, which the
majority-negative cell cannot inflate: positive-specific agreement PA+ (the chance two
labelers both call a change risky, among changes either marked risky), per-class PA+,
and the A x B coarse confusion matrix. Pure stdlib; reads the two labeler CSVs.

Used in Section IV-F to preempt the "NONE-inflated κ" attack (PA+ = 0.903).
"""
import csv
import collections
import json
import sys

A_PATH = "results/tse_gap_closure/data/labels_A.csv"
B_PATH = "results/tse_gap_closure/data/labels_B.csv"
OUT = "results/tse_gap_closure/data/positive_class_agreement.json"


def coarse(x):
    for p in ("P1", "P2", "P3"):
        if x.startswith(p):
            return p
    return "NONE"


def load(path):
    return {r["change_id"]: coarse(r["label_primary"]) for r in csv.DictReader(open(path))}


def main():
    A, B = load(A_PATH), load(B_PATH)
    keys = set(A) & set(B)
    cls = ["NONE", "P1", "P2", "P3"]
    cm = collections.Counter((A[k], B[k]) for k in keys)

    # positive-specific agreement PA+ = 2*both_risky / (A_risky + B_risky)
    both = sum(cm[(a, b)] for a in cls[1:] for b in cls[1:])  # both non-NONE
    a_pos = sum(cm[(a, b)] for a in cls[1:] for b in cls)
    b_pos = sum(cm[(a, b)] for a in cls for b in cls[1:])
    pa_plus = 2 * both / (a_pos + b_pos)

    per_class = {}
    for c in ("P1", "P2", "P3"):
        bc = cm[(c, c)]
        ea = sum(cm[(c, b)] for b in cls)
        eb = sum(cm[(a, c)] for a in cls)
        per_class[c] = round(2 * bc / max(ea + eb, 1), 3)

    p3_discord = cm[("P3", "NONE")] + cm[("NONE", "P3")]
    out = {
        "n_shared": len(keys),
        "PA_plus_positive_specific": round(pa_plus, 3),
        "per_class_PA_plus": per_class,
        "confusion_A_row_B_col": {f"{a}|{b}": cm[(a, b)] for a in cls for b in cls if cm[(a, b)]},
        "P3_borderline_discordances": p3_discord,
        "_note": "PA+ restricts agreement to the positive classes; not inflated by the 96.8% NONE cell.",
    }
    json.dump(out, open(OUT, "w"), indent=2)
    print(json.dumps(out, indent=2))
    print(f"-> {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()

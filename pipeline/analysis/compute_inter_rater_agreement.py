"""
Inter-rater agreement for risk-positive annotation (Workstream D.6).

Implements:
  cohen_kappa(r1, r2)              — pairwise Cohen's kappa for two raters
  pairwise_kappa(ratings_dict)     — all rater pairs from dict{name: [labels]}
  krippendorff_alpha_nominal(data) — Krippendorff alpha for nominal labels;
                                     data is list of items, each a list of
                                     judgments (missing = None is skipped)
"""

import csv
from collections import Counter
from itertools import combinations
from pathlib import Path


def cohen_kappa(r1, r2):
    """Cohen's kappa for two raters with equal-length label lists."""
    if len(r1) != len(r2):
        raise ValueError(f"rater lists differ in length: {len(r1)} vs {len(r2)}")
    if not r1:
        raise ValueError("empty rater lists")

    n = len(r1)
    labels = sorted(set(r1) | set(r2))

    # observed agreement
    po = sum(a == b for a, b in zip(r1, r2)) / n

    # expected agreement (product of marginals)
    c1 = Counter(r1)
    c2 = Counter(r2)
    pe = sum((c1[lbl] / n) * (c2[lbl] / n) for lbl in labels)

    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1.0 - pe)


def pairwise_kappa(ratings):
    """Compute Cohen's kappa for every rater pair.

    ratings: dict mapping rater_id -> list of labels (same order, same length)
    Returns dict mapping "raterA_vs_raterB" -> kappa float.
    """
    result = {}
    names = sorted(ratings.keys())
    for a, b in combinations(names, 2):
        key = f"{a}_vs_{b}"
        result[key] = cohen_kappa(ratings[a], ratings[b])
    return result


def krippendorff_alpha_nominal(data):
    """Krippendorff's alpha for nominal data.

    data: list of items; each item is a list of judgments (str or None).
    None values are treated as missing and skipped.
    Returns alpha float in [-1, 1].
    """
    # Flatten all non-None judgments for global counts
    all_labels = []
    for item in data:
        for j in item:
            if j is not None:
                all_labels.append(j)

    if not all_labels:
        return 0.0

    n_total = len(all_labels)
    label_counts = Counter(all_labels)
    labels = sorted(label_counts.keys())

    # coincidence matrix accumulation
    # d_o: observed disagreements; d_e: expected disagreements
    # For nominal metric: delta = 0 if same, 1 if different

    # Count pairable judgments per item
    d_o_num = 0.0
    d_o_den = 0.0

    for item in data:
        present = [j for j in item if j is not None]
        m = len(present)
        if m < 2:
            continue
        pairs_agree = sum(1 for i in range(m) for j in range(i + 1, m) if present[i] == present[j])
        pairs_total = m * (m - 1) / 2
        d_o_num += pairs_total - pairs_agree  # disagreeing pairs
        d_o_den += pairs_total

    if d_o_den == 0:
        return 1.0

    d_o = d_o_num / d_o_den

    # Expected disagreement: probability two random labels differ
    pe_agree = sum((cnt / n_total) ** 2 for cnt in label_counts.values())
    d_e = 1.0 - pe_agree

    if d_e == 0:
        return 1.0

    return 1.0 - (d_o / d_e)


def compute_from_csv(csv_path, case_id_col="case_id", label_col="label",
                     annotator_col="annotator_id"):
    """Read annotation CSV and compute IRR across annotators.

    Returns dict with pairwise kappas, krippendorff alpha, and per-rater counts.
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        return {"error": "empty CSV"}

    # Group by case_id
    from collections import defaultdict
    by_case = defaultdict(dict)
    for row in rows:
        cid = row[case_id_col]
        ann = row[annotator_col]
        lbl = row[label_col]
        if ann and lbl:
            by_case[cid][ann] = lbl

    raters = sorted({ann for item in by_case.values() for ann in item})
    if len(raters) < 2:
        return {"error": f"need ≥2 annotators, found: {raters}"}

    # Build per-rater label lists (items where both raters gave a label)
    common_cases = [
        cid for cid, anns in by_case.items()
        if all(r in anns for r in raters)
    ]
    if not common_cases:
        return {"error": "no cases with all raters annotated"}

    ratings = {r: [by_case[cid][r] for cid in common_cases] for r in raters}

    # Krippendorff: data as list of items, each item's judgments in order
    kripp_data = [[by_case[cid].get(r) for r in raters] for cid in common_cases]

    return {
        "n_cases_annotated": len(common_cases),
        "raters": raters,
        "pairwise_kappa": pairwise_kappa(ratings),
        "krippendorff_alpha_nominal": krippendorff_alpha_nominal(kripp_data),
    }


if __name__ == "__main__":
    import argparse, json
    parser = argparse.ArgumentParser(description="Compute IRR from annotation CSV")
    parser.add_argument("csv", help="Annotation CSV path")
    parser.add_argument("--case-id-col", default="case_id")
    parser.add_argument("--label-col", default="label")
    parser.add_argument("--annotator-col", default="annotator_id")
    args = parser.parse_args()

    result = compute_from_csv(args.csv, args.case_id_col, args.label_col, args.annotator_col)
    print(json.dumps(result, indent=2))

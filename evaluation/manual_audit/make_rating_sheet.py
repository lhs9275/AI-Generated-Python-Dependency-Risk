#!/usr/bin/env python3
"""Generate BLIND inter-rater reliability sheets for the F4/F6 manual audit.

Two raters independently fill rating_sheet_rater{1,2}.csv WITHOUT seeing the
guard's own decision/labels (the system answer is hidden to avoid anchoring).
merge_ratings.py then re-joins the hidden stratification metadata into
results.csv, which compute_irr.py consumes.

Run: python evaluation/manual_audit/make_rating_sheet.py
"""
import csv
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
META = os.path.join(HERE, "sample_meta.json")

_BOILERPLATE = [
    "# Task Instructions",
    "You are a Python developer working on a small project repository.",
    "Your goal is to implement the required functionality described below.",
]


def task_requirement(task_id):
    """Pull a short, neutral requirement excerpt from the task prompt (no oracle info)."""
    hits = glob.glob(os.path.join(ROOT, "bench", "*", task_id, "prompt.md"))
    if not hits:
        return ""
    txt = open(hits[0], encoding="utf-8").read()
    for b in _BOILERPLATE:
        txt = txt.replace(b, "")
    txt = re.sub(r"^#.*$", "", txt, flags=re.M)          # drop markdown headers
    txt = re.sub(r"\n{2,}", "\n", txt).strip()
    return txt[:600].replace("\n", " / ")


def main():
    meta = json.load(open(META, encoding="utf-8"))
    rows = []
    for e in meta:
        deps = e.get("dep_changes", [])
        rows.append({
            "sample_id": e["sample_id"],
            "family": e["family"],                         # F4=license, F6=unnecessary-dep
            "condition": e.get("condition", ""),
            "added_packages": ", ".join(d["package"] for d in deps),
            "dependency_change": " | ".join(
                f'{d.get("new_line") or d["package"]} [{d.get("file", "?")}]' for d in deps),
            "task_requirement": task_requirement(e["task_id"]),
            # ---- raters fill these (everything else is read-only context) ----
            "safety_pass_core": "",      # ALL rows: yes / no / unclear
            "unnecessary_dep": "",       # F6 rows ONLY: yes / no / unclear (blank for F4)
            "license_violation": "",     # F4 rows ONLY: yes / no / unclear (blank for F6)
            "rationale": "",
        })

    cols = ["sample_id", "family", "condition", "added_packages", "dependency_change",
            "task_requirement", "safety_pass_core", "unnecessary_dep", "license_violation",
            "rationale"]
    for rater in ("rater1", "rater2"):
        path = os.path.join(HERE, f"rating_sheet_{rater}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        print("wrote", path)
    n4 = sum(r["family"] == "F4" for r in rows)
    n6 = sum(r["family"] == "F6" for r in rows)
    print(f"{len(rows)} blinded samples (F4={n4}, F6={n6}). System decision/labels are HIDDEN.")


if __name__ == "__main__":
    main()

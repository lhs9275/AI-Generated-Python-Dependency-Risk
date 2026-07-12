"""
Recompute benchmark metrics after the dependency-parser fix.

WHY
---
The historical benchmark dep-extractor (prefix-only regex) turned source lines
that agents accidentally wrote into requirements.txt (``import re``, a dumped
``<<<FILE: ...>>>`` block, ``def foo():`` ...) into bogus "packages" such as
``import``. Both the Guard AND the independent safety oracle then consumed those
artifacts — the oracle even labels ``import`` as ``unnecessary_dependency`` — so
a handful of CodeLlama runs are scored risky for a parsing artifact, inflating
the CodeLlama F6 residual (42.5% -> 37.5%) and overall B3 RiskyAcc (7.5% -> 6.7%).

dep_extractor.py is now fixed (each line is validated as a real PEP 508
requirement). This script applies that fix retroactively to the stored
result.json files WITHOUT re-running any LLM or GPU work:

  1. Re-derive cleaned dep_changes for every run (the fix only ever REMOVES
     invalid lines, so cleaning the stored dep_changes == re-extraction here).
  2. Re-run the independent safety oracle on the cleaned dep_changes.
  3. Re-run the Guard for every deterministic mode (B0/B1/B2/B3 and the R*
     repair modes); reuse the test-based functional oracle unchanged.
  4. Recompute metrics_by_mode and the top-level metrics.
  5. Report the before/after delta. Scanner modes (B1_scanner/B2_scanner) need
     pip-audit/venv and are preserved untouched.

USAGE
-----
  # GPU-free. Run from the repo root.
  python -m pipeline.recompute_fixed_parser                 # dry-run (default): report only
  python -m pipeline.recompute_fixed_parser --model CodeLlama-7b-Instruct-hf
  python -m pipeline.recompute_fixed_parser --apply         # write corrected values back

  # After --apply, refresh the paper tables / artifacts:
  python pipeline/build_tables.py
  python pipeline/reproduce_tables.py
  python pipeline/compute_ablation.py            # if present, to refresh ablation_raw
  python -m pipeline.compute_additional_baselines

--apply writes a one-time backup result.json.prebug.bak next to each modified
file and is idempotent (re-running changes nothing once clean).

Outputs:
  results/parser_recompute_report.md
  results/parser_recompute_changes.csv
"""

import argparse
import os
import csv
import json
from collections import defaultdict
from pathlib import Path

from .dep_extractor import _is_valid_requirement_line, _NON_PKG_TOKENS, extract_changes, load_requirements
from .guard.decision import run_guard
from .adjudicator.safety_oracle import compute as compute_safety
from .adjudicator.metric_calculator import compute as compute_metrics

import yaml

RESULTS_DIR = Path("results")
BENCH_ROOT  = Path("bench")
REPORT_MD   = RESULTS_DIR / "parser_recompute_report.md"
REPORT_CSV  = RESULTS_DIR / "parser_recompute_changes.csv"

# Deterministic guard modes recomputable here (depend only on dep_changes +
# evidence + policy). Scanner modes require pip-audit and are left untouched.
DETERMINISTIC_MODES = ["B0", "B1", "B2", "B3", "B1_deterministic", "B2_deterministic"]

MODEL_DISPLAY = {
    "Qwen2.5-Coder-7B-Instruct":      "Qwen-7B",
    "Qwen2.5-Coder-14B-Instruct-AWQ": "Qwen-14B",
    "Qwen2.5-Coder-32B-Instruct-AWQ": "Qwen-32B",
    "deepseek-coder-6.7b-instruct":   "DeepSeek-6.7B",
    "CodeLlama-7b-Instruct-hf":       "CodeLlama-7B",
}


def _bench_task_dir(task_id: str) -> Path | None:
    fam = task_id.split("_")[1]
    for d in BENCH_ROOT.iterdir():
        if d.is_dir() and d.name.startswith(fam + "_"):
            cand = d / task_id
            if cand.exists():
                return cand
    return None


def _load_bench_meta(task_id: str):
    td = _bench_task_dir(task_id)
    if not td:
        return None
    ev = json.loads((td / "evidence_refs.json").read_text()) if (td / "evidence_refs.json").exists() else {}
    po = yaml.safe_load((td / "dependency_policy.yaml").read_text()) if (td / "dependency_policy.yaml").exists() else {}
    orc = yaml.safe_load((td / "risk_oracle.yaml").read_text()) if (td / "risk_oracle.yaml").exists() else {}
    orig_req = load_requirements(td / "repo")
    return {"evidence": ev, "policy": po, "oracle": orc, "orig_req": orig_req, "dir": td}


def clean_dep_changes(dep_changes: list[dict]) -> tuple[list[dict], list[str]]:
    """Drop entries that are parser artifacts (source tokens / non-requirement
    lines). Returns (cleaned, dropped_package_names)."""
    cleaned, dropped = [], []
    for c in dep_changes or []:
        pkg = str(c.get("package", "")).lower().replace("-", "_")
        # the line that defines this change (added/modified use new_line)
        line = c.get("new_line") or c.get("original_line") or c.get("package") or ""
        if pkg in _NON_PKG_TOKENS or not _is_valid_requirement_line(str(line)):
            dropped.append(c.get("package", ""))
            continue
        cleaned.append(c)
    return cleaned, dropped


def recompute_run(r: dict, meta: dict, run_repo: Path | None) -> dict | None:
    """Return the recomputed {dep_changes, adjudication, metrics_by_mode, metrics}
    using the fixed parser, or None if nothing to recompute."""
    ev, po, orc = meta["evidence"], meta["policy"], meta["oracle"]

    # Prefer faithful re-extraction from the stored repo; fall back to cleaning.
    if run_repo is not None and (run_repo / "requirements.txt").exists():
        new_req = load_requirements(run_repo)
        new_dep_changes = extract_changes(meta["orig_req"], new_req)
        dropped = sorted({c.get("package") for c in (r.get("dep_changes") or [])}
                         - {c.get("package") for c in new_dep_changes})
    else:
        new_dep_changes, dropped = clean_dep_changes(r.get("dep_changes"))

    func_result = r.get("adjudication", {}).get("functional")
    if func_result is None:
        return None
    safety_new = compute_safety(new_dep_changes, ev, orc)

    # Repair iterations: clean their stored dep_changes (repair repos are not
    # preserved under results/), re-run safety+guard for each.
    iter_adj = []
    for it in r.get("repair_iterations", []) or []:
        rdc, _ = clean_dep_changes(it.get("dep_changes"))
        iter_adj.append({
            "iter": it["iter"],
            "func": _func_from_iter(r, it["iter"]),
            "safety": compute_safety(rdc, ev, orc),
            "guard": run_guard(rdc, ev, po, mode="B3"),
        })

    guard_by_mode = {m: run_guard(new_dep_changes, ev, po, mode=m) for m in ("B0", "B1", "B2", "B3")}
    guard_by_mode["B1_deterministic"] = {**guard_by_mode["B1"], "mode": "B1_deterministic"}
    guard_by_mode["B2_deterministic"] = {**guard_by_mode["B2"], "mode": "B2_deterministic"}

    new_mbm = dict(r.get("metrics_by_mode", {}))   # start from old; overwrite deterministic
    for m in DETERMINISTIC_MODES:
        g = guard_by_mode.get(m)
        if g is not None:
            new_mbm[m] = compute_metrics(func_result, safety_new, g, None, None, None)
    for adj in iter_adj:
        new_mbm[f"R{adj['iter']}"] = compute_metrics(
            func_result, safety_new, guard_by_mode["B3"], adj["func"], adj["safety"], adj["guard"])

    return {
        "dep_changes": new_dep_changes,
        "dropped": [d for d in dropped if d],
        "adjudication": {"functional": func_result, "safety": safety_new},
        "guard_by_mode": {**r.get("guard_by_mode", {}), **guard_by_mode},
        "metrics_by_mode": new_mbm,
    }


def _func_from_iter(r: dict, k: int):
    """Best-effort functional result for repair iteration k from stored data."""
    # stored result.json doesn't always keep per-iter adjudication; reuse the
    # iteration's own tests if present, else the top-level functional.
    for it in r.get("repair_iterations", []) or []:
        if it["iter"] == k and "public_tests" in it and "hidden_tests" in it:
            pt, ht = it["public_tests"], it["hidden_tests"]
            total = pt.get("total", 0) + ht.get("total", 0)
            passed = pt.get("passed", 0) + ht.get("passed", 0)
            return {"functional_success": total > 0 and passed == total,
                    "public_passed": pt.get("passed", 0) == pt.get("total", 0),
                    "hidden_passed": ht.get("passed", 0) == ht.get("total", 0),
                    "detail": "recomputed from iter tests"}
    return r.get("adjudication", {}).get("functional")


def _risky(mbm, mode):
    return bool(mbm.get(mode, {}).get("accepted", {}).get("risky_accepted_patch"))


def main():
    ap = argparse.ArgumentParser(description="Recompute benchmark metrics with the fixed dep parser.")
    ap.add_argument("--apply", action="store_true",
                    help="Write corrected dep_changes/adjudication/metrics back to result.json (with .prebug.bak backup). Default: dry-run report only.")
    ap.add_argument("--model", default=None,
                    help="Restrict to one model slug substring (e.g. CodeLlama-7b-Instruct-hf).")
    args = ap.parse_args()

    meta_cache: dict[str, dict] = {}
    changed_rows = []
    # per-model dedup primary tallies, before vs after
    before = defaultdict(lambda: defaultdict(lambda: [0, 0]))   # model -> mode -> [risky, n]
    after  = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    by_key = {}  # (task,cond,model) -> (mtime, path)

    paths = sorted(RESULTS_DIR.glob("task_*/*/result.json"))
    n_scanned = n_changed = 0
    for p in paths:
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        slug = r.get("model_id", "").rsplit("/", 1)[-1]
        if slug not in MODEL_DISPLAY:
            continue
        if args.model and args.model not in slug:
            continue
        if "metrics_by_mode" not in r or "task_id" not in r:
            continue
        n_scanned += 1

        task_id = r["task_id"]
        if task_id not in meta_cache:
            m = _load_bench_meta(task_id)
            if m is None:
                continue
            meta_cache[task_id] = m
        meta = meta_cache[task_id]

        rc = recompute_run(r, meta, p.parent / "repo")
        if rc is None:
            continue

        # did anything change?
        old_pkgs = sorted(c.get("package") for c in (r.get("dep_changes") or []))
        new_pkgs = sorted(c.get("package") for c in rc["dep_changes"])
        mode_flips = [m for m in ("B0", "B1", "B2", "B3")
                      if _risky(r.get("metrics_by_mode", {}), m) != _risky(rc["metrics_by_mode"], m)]
        run_changed = (old_pkgs != new_pkgs) or bool(mode_flips)

        # tally for dedup primary (latest mtime per task,cond,model)
        key = (task_id, r["generation_condition"], slug)
        mt = p.stat().st_mtime
        if key not in by_key or mt > by_key[key][0]:
            by_key[key] = (mt, r, rc)

        if run_changed:
            n_changed += 1
            changed_rows.append({
                "task_id": task_id, "cond": r["generation_condition"], "model": MODEL_DISPLAY[slug],
                "run_dir": p.parent.name,
                "dropped_pkgs": ",".join(rc["dropped"]) or "(none)",
                "old_added": ",".join(c.get("package") for c in (r.get("dep_changes") or []) if c.get("change_type") == "added") or "(none)",
                "new_added": ",".join(c.get("package") for c in rc["dep_changes"] if c.get("change_type") == "added") or "(none)",
                "B0_risky_old": _risky(r.get("metrics_by_mode", {}), "B0"), "B0_risky_new": _risky(rc["metrics_by_mode"], "B0"),
                "B3_risky_old": _risky(r.get("metrics_by_mode", {}), "B3"), "B3_risky_new": _risky(rc["metrics_by_mode"], "B3"),
            })

        if args.apply and run_changed:
            bak = p.with_suffix(".json.prebug.bak")
            if not bak.exists():
                bak.write_text(p.read_text())
            r["dep_changes"] = rc["dep_changes"]
            r["adjudication"] = rc["adjudication"]
            r["guard_by_mode"] = rc["guard_by_mode"]
            r["metrics_by_mode"] = rc["metrics_by_mode"]
            r["metrics"] = rc["metrics_by_mode"].get("R1", rc["metrics_by_mode"].get("B3"))
            r["_parser_fix_applied"] = True
            # Preserve the original mtime: run selection elsewhere dedups by
            # latest mtime per (task, cond), so rewriting must NOT reorder runs.
            orig = p.stat()
            p.write_text(json.dumps(r, ensure_ascii=False, indent=2))
            os.utime(p, (orig.st_atime, orig.st_mtime))

    # dedup primary before/after tallies
    for key, (mt, r, rc) in by_key.items():
        model = MODEL_DISPLAY[r.get("model_id", "").rsplit("/", 1)[-1]]
        fam = key[0].split("_")[1]
        for mode in ("B0", "B3"):
            before[model][mode][1] += 1; after[model][mode][1] += 1
            if _risky(r.get("metrics_by_mode", {}), mode): before[model][mode][0] += 1
            if _risky(rc["metrics_by_mode"], mode):         after[model][mode][0] += 1
        # F6 residual (B3)
        if fam == "F6":
            before[model]["F6_B3"][1] += 1; after[model]["F6_B3"][1] += 1
            if _risky(r.get("metrics_by_mode", {}), "B3"): before[model]["F6_B3"][0] += 1
            if _risky(rc["metrics_by_mode"], "B3"):        after[model]["F6_B3"][0] += 1

    # ---- report ----
    def pct(d):
        return f"{100*d[0]/d[1]:.1f}% ({d[0]}/{d[1]})" if d[1] else "—"

    mode_label = "APPLIED" if args.apply else "DRY-RUN (no files modified)"
    md = [f"# Parser-fix recomputation report ({mode_label})\n",
          f"Scanned {n_scanned} runs; {n_changed} changed.\n",
          "## Deduplicated primary RiskyAcc — before vs after fix\n",
          "| Model | B0 before | B0 after | B3 before | B3 after | F6@B3 before | F6@B3 after |",
          "|-------|-----------|----------|-----------|----------|--------------|-------------|"]
    for model in ["Qwen-7B", "Qwen-14B", "Qwen-32B", "DeepSeek-6.7B", "CodeLlama-7B"]:
        if before[model]["B0"][1] == 0:
            continue
        md.append(f"| {model} | {pct(before[model]['B0'])} | {pct(after[model]['B0'])} | "
                  f"{pct(before[model]['B3'])} | {pct(after[model]['B3'])} | "
                  f"{pct(before[model]['F6_B3'])} | {pct(after[model]['F6_B3'])} |")
    md += ["\n## Changed runs\n",
           "See results/parser_recompute_changes.csv "
           f"({len(changed_rows)} run(s)). " +
           ("Files were updated in place (backups: *.json.prebug.bak)."
            if args.apply else "Re-run with --apply to write these back.")]
    REPORT_MD.write_text("\n".join(md))

    if changed_rows:
        keys = list(changed_rows[0].keys())
        with REPORT_CSV.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader(); w.writerows(changed_rows)

    print("\n".join(md))
    print(f"\nWrote {REPORT_MD}")
    if changed_rows:
        print(f"Wrote {REPORT_CSV}")
    if not args.apply:
        print("\n(DRY-RUN) No result.json modified. Add --apply to persist, then re-run build_tables.py / reproduce_tables.py.")


if __name__ == "__main__":
    main()

"""
Minimal demonstration that AgentSupplyGuard runs on PR-time public evidence only.

Auto-selects a benchmark task with a populated frozen evidence snapshot, then runs
the guard (B3) on dependency changes derived from that snapshot:
  (a) a real package at a valid pinned version      -> expect no S1/S2 block
  (b) the same package at an invalid/unreleased pin -> expect S2 BLOCK
  (c) a 1-char typo of the real package name        -> expect S1 BLOCK
This is an artifact smoke test, not an evaluation. No GPU, no network (snapshot
only), no oracle (guard reads evidence_refs + dependency_policy only).

Usage:  python -m pipeline.run_guard_on_examples
"""

import glob
import json
from pathlib import Path

import yaml

from pipeline.guard.decision import run_guard


def _pick_task():
    """First task whose snapshot has a real date and >=1 existing package with versions."""
    for ev in sorted(glob.glob("bench/*/task_*/evidence_refs.json")):
        e = json.loads(Path(ev).read_text())
        if "FILL" in str(e.get("snapshot_date", "")):
            continue
        for name, info in (e.get("pypi_packages") or {}).items():
            if info.get("exists") and info.get("known_versions"):
                return Path(ev).parent, e, name, info
    raise SystemExit("no populated snapshot found")


def main():
    task_dir, evidence, pkg, info = _pick_task()
    policy = yaml.safe_load((task_dir / "dependency_policy.yaml").read_text())
    valid_v = info["known_versions"][-1]
    typo = pkg[:-1] + ("x" if not pkg.endswith("x") else "z")

    print(f"Task: {task_dir.name}   snapshot: {evidence.get('snapshot_date')} "
          f"({len(evidence.get('pypi_packages', {}))} pkgs, "
          f"{len(evidence.get('vulnerability_advisories', {}))} advisories)")
    print(f"Real package under test: {pkg} (valid versions incl. {valid_v})\n")

    examples = [
        (f"real package + valid pin (expect no S1/S2 block)",
         {"package": pkg, "new_line": f"{pkg}=={valid_v}", "specifier": f"=={valid_v}"}),
        (f"invalid/unreleased version pin (expect S2 BLOCK)",
         {"package": pkg, "new_line": f"{pkg}==99.99.99", "specifier": "==99.99.99"}),
        (f"hallucinated typo name '{typo}' (expect S1 BLOCK)",
         {"package": typo, "new_line": f"{typo}=={valid_v}", "specifier": f"=={valid_v}"}),
    ]

    for label, ch in examples:
        change = {"original_line": None, "change_type": "added",
                  "file": "requirements.txt", **ch}
        res = run_guard([change], evidence, policy, mode="B3")
        fired = [s for s, v in res["stages"].items() if v["decision"] == "BLOCK"]
        print(f"- {label}")
        print(f"    {change['new_line']!r}  ->  decision={res['decision']}"
              f"  (BLOCK stages: {fired or 'none'})")
        for issue in res["risk_report"]:
            if issue.get("stage") in {"S1", "S2", "S3"}:
                print(f"    {issue.get('stage')}: {issue.get('reason')}")
        print()

    print("OK: guard executed against frozen public evidence only (no oracle, no network).")


if __name__ == "__main__":
    main()

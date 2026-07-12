"""
Workstream H — agentic baseline table (RQ2).

Source: data/agentic/runs_model_d_scored.jsonl — a current repository-grounded
multi-turn tool-calling agent (model_d = Qwen2.5-Coder-14B) run on the controlled
benchmark under four native-validation conditions (60 tasks each):
  agent_native_no_gate           no validation
  agent_native_with_public_tests agent may run the public test suite
  agent_native_with_pip_dry_run  agent may run a pip dry-run install
  agent_with_guard_observation   agent sees the dependency-guard observation

Metrics (per docs: "2026 agentic relevance and residual risk after native
validation"):
  native_agent_RiskyAcc          risky deps accepted with NO gate
  after_public_tests             RiskyAcc when the agent can run public tests
  after_pip_dry_run              RiskyAcc when the agent can run pip dry-run
  with_guard_observation         RiskyAcc when the agent sees the guard
  B3_residual_RiskyAcc           risky deps that survive a B3 gate applied post-hoc
  minimal_gate_RiskyAcc          risky deps that survive an S1+S2+S3 gate post-hoc
  FuncSucc per condition + delta vs no_gate

B3_residual uses the per-record B3_score from the agentic scorer. minimal_gate is
recomputed by running run_guard(mode="S1_S2_S3") on each risky record's actual
manifest change (S1_S2_S3 ⊆ B3 stages ⇒ minimal-gate residual ≥ B3 residual).
"""
import json
from collections import defaultdict
from pathlib import Path

import yaml

from pipeline.dep_extractor import extract_changes, load_requirements
from pipeline.guard.decision import run_guard

SCORED = Path("data/agentic/runs_model_d_scored.jsonl")
BENCH_ROOT = Path("bench")

CONDITIONS = [
    "agent_native_no_gate",
    "agent_native_with_public_tests",
    "agent_native_with_pip_dry_run",
    "agent_with_guard_observation",
]


def _find_task_dir(task_id):
    for fam in BENCH_ROOT.iterdir():
        p = fam / task_id
        if p.exists():
            return p
    return None


def _minimal_gate_blocks(rec) -> bool | None:
    """True if an S1+S2+S3 gate would BLOCK this record's manifest change.
    None if it cannot be evaluated (no manifest diff / missing task)."""
    diff = rec.get("final_manifest_diff") or {}
    new_req = diff.get("requirements.txt")
    if not new_req:
        return None
    task_dir = _find_task_dir(rec["task_id"])
    if task_dir is None:
        return None
    try:
        original = load_requirements(task_dir / "repo")
        dep_changes = extract_changes(original, new_req)
        evidence = json.loads((task_dir / "evidence_refs.json").read_text())
        policy = yaml.safe_load((task_dir / "dependency_policy.yaml").read_text())
        res = run_guard(dep_changes, evidence, policy, mode="S1_S2_S3")
        return res.get("decision") == "BLOCK"
    except Exception:
        return None


def build_rq2() -> list[dict]:
    recs = [json.loads(l) for l in open(SCORED)]
    by_cond = defaultdict(list)
    for r in recs:
        by_cond[r["condition"]].append(r)

    # FuncSucc baseline (no_gate) for delta.
    def _rate(rows, key):
        n = len(rows)
        k = sum(1 for r in rows if r.get(key))
        return (k, n, round(k / n, 4) if n else None)

    base_fs = _rate(by_cond.get("agent_native_no_gate", []), "FuncSucc")[2]

    rows = []
    for cond in CONDITIONS:
        rows_c = by_cond.get(cond, [])
        if not rows_c:
            continue
        rk, rn, rr = _rate(rows_c, "RiskyAcc")
        fk, fn, fr = _rate(rows_c, "FuncSucc")
        # B3 residual: risky AND B3 did not block (B3_score == PASS/WARN).
        b3_resid = sum(1 for r in rows_c
                       if r.get("RiskyAcc") and r.get("B3_score") in ("PASS", "WARN", None))
        # Minimal-gate residual: risky AND S1+S2+S3 would not block.
        min_resid = 0
        min_evaluated = 0
        for r in rows_c:
            if not r.get("RiskyAcc"):
                continue
            blocks = _minimal_gate_blocks(r)
            if blocks is None:
                continue
            min_evaluated += 1
            if not blocks:
                min_resid += 1
        rows.append({
            "condition": cond,
            "n": rn,
            "RiskyAcc": rr,
            "n_risky": rk,
            "FuncSucc": fr,
            "FuncSucc_delta_vs_no_gate":
                round(fr - base_fs, 4) if (fr is not None and base_fs is not None) else "",
            "B3_residual_RiskyAcc_count": b3_resid,
            "B3_residual_RiskyAcc_rate": round(b3_resid / rn, 4) if rn else "",
            "minimal_gate_residual_count": min_resid,
            "minimal_gate_evaluated": min_evaluated,
        })
    return rows


if __name__ == "__main__":
    for r in build_rq2():
        print(json.dumps(r, default=str))

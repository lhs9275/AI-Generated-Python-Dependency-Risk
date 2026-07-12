"""
Build commercial agent task assignment CSV and results template CSV (Workstream F).

Usage:
  python -m pipeline.agentic.build_commercial_assignments
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

AGENTS = ["codex", "copilot", "claude_code", "cursor", "devin"]
FAMILIES = ["F1", "F2", "F3", "F4", "F5", "F6"]
N_PER_FAMILY = 10

ASSIGNMENT_COLS = [
    "agent_name", "task_id", "risk_family", "task_dir",
    "status", "assigned_to", "notes",
]

RESULT_COLS = [
    "run_id", "agent_name", "task_id", "risk_family", "model_name",
    "condition", "started_at", "finished_at", "num_turns",
    "commands_run_count", "public_tests_passed", "public_tests_failed",
    "final_patch_path", "dep_changes_count",
    "B0_decision", "B1_decision", "B3_decision",
    "RiskyAcc", "FuncSucc", "AFSP", "DIR", "failure_mode", "notes",
]


def select_tasks(bench_dir: Path) -> list:
    tasks = []
    for fam in FAMILIES:
        fam_tasks = sorted(bench_dir.glob(f"{fam}_*/task_{fam}_*"))[:N_PER_FAMILY]
        for t in fam_tasks:
            tasks.append((fam, t.name, str(t)))
    return tasks


def build_assignments(bench_dir: Path) -> list:
    tasks = select_tasks(bench_dir)
    rows = []
    for agent in AGENTS:
        for fam, task_id, task_dir in tasks:
            rows.append({
                "agent_name": agent,
                "task_id": task_id,
                "risk_family": fam,
                "task_dir": task_dir,
                "status": "pending",
                "assigned_to": "",
                "notes": "",
            })
    return rows


def build_results_template(bench_dir: Path) -> list:
    tasks = select_tasks(bench_dir)
    rows = []
    for agent in AGENTS:
        for fam, task_id, _ in tasks:
            rows.append({col: "" for col in RESULT_COLS} | {
                "agent_name": agent,
                "task_id": task_id,
                "risk_family": fam,
                "condition": "agent_final_patch_scored_by_B0_B1_B3",
                "failure_mode": "",
            })
    return rows


def main():
    bench_dir = Path("bench")
    out_assignments = Path("data/agentic/commercial_agent_task_assignments.csv")
    out_results = Path("results/agentic/commercial_agent_results_template.csv")

    out_assignments.parent.mkdir(parents=True, exist_ok=True)
    out_results.parent.mkdir(parents=True, exist_ok=True)

    assignments = build_assignments(bench_dir)
    with open(out_assignments, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ASSIGNMENT_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(assignments)

    results_tmpl = build_results_template(bench_dir)
    with open(out_results, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(results_tmpl)

    print(f"Assignments: {len(assignments)} rows → {out_assignments}")
    print(f"Results template: {len(results_tmpl)} rows → {out_results}")
    print(f"  {len(AGENTS)} agents × {N_PER_FAMILY * len(FAMILIES)} tasks = {len(results_tmpl)}")


if __name__ == "__main__":
    main()

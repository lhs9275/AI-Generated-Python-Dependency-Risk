"""
Workstream E: CLI runner for agentic baseline experiments.

Runs the AgentHarness over a stratified task subset (or custom task list)
and appends each run manifest to data/agentic/agent_runs_manifest.json.

Usage (single task, smoke test):
  python -m pipeline.agentic.run_agentic_tasks \\
    --task bench/F1_package_existence/task_F1_001 \\
    --model Qwen2.5-Coder-7B-Instruct \\
    --condition agent_native_with_public_tests \\
    --max-turns 10 \\
    --results-dir results/agentic

Usage (stratified 60-task subset):
  python -m pipeline.agentic.run_agentic_tasks \\
    --bench bench/ \\
    --model Qwen2.5-Coder-7B-Instruct \\
    --condition agent_native_with_public_tests \\
    --n-per-family 10 \\
    --max-turns 10 \\
    --results-dir results/agentic

Usage (smoke test — 1 task per family, no LLM):
  python -m pipeline.agentic.run_agentic_tasks \\
    --bench bench/ --smoke-test \\
    --results-dir results/agentic/smoke

GPU submission (run on a GPU node):
  python -m pipeline.agentic.run_agentic_tasks \\
    --bench bench/ \\
    --model Qwen2.5-Coder-7B-Instruct \\
    --condition agent_native_with_public_tests \\
    --n-per-family 10 --results-dir results/agentic
"""

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.agentic.agent_harness import AgentHarness, CONDITION_TOOLS

FAMILIES = ["F1", "F2", "F3", "F4", "F5", "F6"]
MANIFEST_PATH = Path("data/agentic/agent_runs_manifest.json")


def select_tasks(bench_dir: Path, n_per_family: int = 10,
                 families: list = None) -> list:
    """Select a stratified subset of tasks from bench_dir.

    Returns list of Path objects, sorted by family + task number.
    """
    bench_dir = Path(bench_dir)
    fams = families or FAMILIES
    selected = []
    for fam in fams:
        fam_dirs = sorted(bench_dir.glob(f"{fam}_*/task_{fam}_*"))
        selected.extend(fam_dirs[:n_per_family])
    return selected


def run_task(task_dir: Path, model_id: str, condition: str,
             results_dir: Path, max_turns: int, seed: int,
             llm_base_url: str = "http://localhost:8000/v1") -> dict:
    """Run a single task and return the manifest."""
    run_id = uuid.uuid4().hex[:8]
    work_dir = results_dir / task_dir.name / run_id

    harness = AgentHarness(
        task_dir=task_dir,
        work_dir=work_dir,
        model_id=model_id,
        condition=condition,
        max_turns=max_turns,
        seed=seed,
        llm_base_url=llm_base_url,
    )
    manifest = harness.run()
    manifest["run_id"] = run_id  # override with top-level run_id

    # Save per-run manifest
    work_dir.mkdir(parents=True, exist_ok=True)
    run_manifest_path = work_dir / "run_manifest.json"
    with open(run_manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)

    return manifest


def append_to_manifest(manifest: dict, manifest_path: Path = MANIFEST_PATH):
    """Append a run manifest to the global manifest JSONL."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "a") as f:
        f.write(json.dumps(manifest, default=str) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run agentic baseline experiments (Workstream E)")
    parser.add_argument("--bench", default="bench",
                        help="Bench directory containing F1-F6 task subdirs")
    parser.add_argument("--task", help="Single task directory (overrides --bench)")
    parser.add_argument("--model", required=True, help="Model ID or path")
    parser.add_argument("--condition", default="agent_native_with_public_tests",
                        choices=list(CONDITION_TOOLS.keys()))
    parser.add_argument("--n-per-family", type=int, default=10,
                        help="Tasks per risk family (E.5 stratified subset)")
    parser.add_argument("--families", nargs="+", default=FAMILIES)
    parser.add_argument("--max-turns", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--results-dir", default="results/agentic")
    parser.add_argument("--llm-base-url", default="http://localhost:8000/v1")
    parser.add_argument("--manifest-out", default=str(MANIFEST_PATH))
    parser.add_argument("--smoke-test", action="store_true",
                        help="1 task per family, max_turns=3 (no LLM call, dry run only)")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest_out)

    if args.task:
        tasks = [Path(args.task)]
    elif args.smoke_test:
        tasks = select_tasks(Path(args.bench), n_per_family=1,
                             families=args.families)
    else:
        tasks = select_tasks(Path(args.bench), n_per_family=args.n_per_family,
                             families=args.families)

    if not tasks:
        print("No tasks found. Check --bench path.", file=sys.stderr)
        sys.exit(1)

    print(f"Running {len(tasks)} tasks | condition={args.condition} | "
          f"model={Path(args.model).name} | max_turns={args.max_turns}")

    max_turns = 3 if args.smoke_test else args.max_turns
    success = 0
    failed = 0

    for i, task_dir in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] {task_dir.name} ...", end=" ", flush=True)
        try:
            manifest = run_task(
                task_dir=task_dir,
                model_id=args.model,
                condition=args.condition,
                results_dir=results_dir,
                max_turns=max_turns,
                seed=args.seed,
                llm_base_url=args.llm_base_url,
            )
            append_to_manifest(manifest, manifest_path)
            fm = manifest.get("failure_mode") or "ok"
            print(f"{fm} ({manifest.get('num_turns',0)} turns)")
            if fm in (None, "", "none", "ok"):
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1

    print(f"\nDone: {success} ok, {failed} failed. Manifest: {manifest_path}")


if __name__ == "__main__":
    main()

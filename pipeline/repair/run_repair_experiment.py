"""
Run R0/R1/R2 repair experiment on a task subset.

Usage:
  python -m pipeline.repair.run_repair_experiment \\
    --bench bench/ \\
    --model Qwen2.5-Coder-7B-Instruct \\
    --mode R2 \\
    --max-iterations 3 \\
    --families F1 F3 \\
    --n-per-family 10 \\
    --llm-base-url http://localhost:8000/v1 \\
    --out results/repair/r2_results.jsonl

Output: JSONL; one record per (task, mode) with all REPAIR_RESULT_FIELDS.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.repair.r2_test_guided_repair import RepairEngine, REPAIR_RESULT_FIELDS
from pipeline.guard.decision import run_guard
from pipeline.test_runner import run_tests


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--bench", default="bench/")
    p.add_argument("--model", required=True)
    p.add_argument("--mode", choices=["R0", "R1", "R2"], default="R2")
    p.add_argument("--max-iterations", type=int, default=3)
    p.add_argument("--families", nargs="*")
    p.add_argument("--n-per-family", type=int, default=10)
    p.add_argument("--llm-base-url", default="http://localhost:8000/v1")
    p.add_argument("--llm-api-key", default="token")
    p.add_argument("--out", default="results/repair/r2_results.jsonl")
    p.add_argument("--smoke-test", action="store_true",
                   help="Use 2 tasks, mock LLM — no real model needed.")
    return p.parse_args()


def select_tasks(bench_dir: Path, families, n_per_family: int) -> list:
    tasks = []
    for fam_dir in sorted(bench_dir.iterdir()):
        if families and fam_dir.name not in families:
            continue
        candidates = sorted(fam_dir.glob("task_*"))[:n_per_family]
        tasks.extend(candidates)
    return tasks


def _make_llm_fn(base_url: str, api_key: str, model: str):
    """Return a callable that sends a repair prompt to the vLLM server."""
    import urllib.request
    import json as _json

    def llm_fn(prompt: str) -> dict:
        payload = _json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
            "temperature": 0.0,
        }).encode()
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = _json.loads(resp.read())
        text = body["choices"][0]["message"]["content"]
        # Minimal patch extraction: look for ```python blocks
        files = {}
        import re
        for m in re.finditer(r"```python\s+#\s*(\S+)\n(.*?)```", text, re.DOTALL):
            files[m.group(1)] = m.group(2)
        return {"files": files, "error": None}

    return llm_fn


def _make_guard_fn(task_dir: Path, policy_path: str = None):
    def guard_fn(patch: dict) -> dict:
        evidence_path = task_dir / "evidence_refs.json"
        policy_path_ = policy_path or str(task_dir / "dependency_policy.yaml")
        if not evidence_path.exists():
            return {"decision": "PASS", "risk_report": [], "repair_feedback": None}
        evidence_refs = json.loads(evidence_path.read_text())
        dep_changes = list(patch.keys())
        return run_guard(dep_changes, evidence_refs, policy_path_, mode="B3")
    return guard_fn


def _make_test_fn(task_dir: Path, work_dir: Path, python: str = "python"):
    def test_fn(patch: dict) -> dict:
        test_dir = task_dir / "tests_public"
        if not test_dir.exists():
            return {"passed": 0, "failed": 0, "errors": 0, "details": []}
        return run_tests(str(work_dir), str(test_dir), python, label="public")
    return test_fn


def run_one(
    task_dir: Path,
    work_dir: Path,
    mode: str,
    max_iterations: int,
    llm_fn,
    model_name: str,
    smoke: bool = False,
) -> dict:
    prompt_path = task_dir / "prompt.md"
    task_prompt = prompt_path.read_text() if prompt_path.exists() else ""

    guard_fn = _make_guard_fn(task_dir)
    test_fn = _make_test_fn(task_dir, work_dir)

    # Initial state: no patch, evaluate from scratch
    initial_guard = guard_fn({})
    initial_func = test_fn({})

    original_result = {
        "guard": initial_guard,
        "func": initial_func,
        "patch": {},
    }

    if smoke:
        def llm_fn(prompt):
            return {"files": {}, "error": None}

    engine = RepairEngine(mode=mode, max_iterations=max_iterations)
    result = engine.run(
        original_result=original_result,
        task_prompt=task_prompt,
        llm_fn=llm_fn,
        guard_fn=guard_fn,
        test_fn=test_fn,
    )

    result["run_id"] = str(uuid.uuid4())
    result["task_id"] = task_dir.name
    result["risk_family"] = task_dir.parent.name
    result["model_name"] = model_name
    result["condition"] = mode
    result["seed"] = 0
    # Placeholders for metrics populated by scorer
    for field in REPAIR_RESULT_FIELDS:
        if field not in result:
            result[field] = None

    return result


def main():
    args = _parse_args()
    bench_dir = Path(args.bench)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tasks = select_tasks(bench_dir, args.families, args.n_per_family)
    if args.smoke_test:
        tasks = tasks[:2]

    llm_fn = _make_llm_fn(args.llm_base_url, args.llm_api_key, args.model)

    print(f"[repair] mode={args.mode} tasks={len(tasks)} max_iters={args.max_iterations}")

    with open(out_path, "a", encoding="utf-8") as f:
        for task_dir in tasks:
            work_dir = task_dir / "_work_repair"
            work_dir.mkdir(parents=True, exist_ok=True)
            try:
                record = run_one(
                    task_dir=task_dir,
                    work_dir=work_dir,
                    mode=args.mode,
                    max_iterations=args.max_iterations,
                    llm_fn=llm_fn,
                    model_name=args.model,
                    smoke=args.smoke_test,
                )
                f.write(json.dumps(record) + "\n")
                f.flush()
                print(f"  {task_dir.name}: mode={record['repair_mode']} "
                      f"iters={record['num_iterations']} "
                      f"failure={record.get('failure_mode', '')}")
            except Exception as exc:
                print(f"  {task_dir.name}: ERROR {exc}", file=sys.stderr)

    print(f"[repair] done → {out_path}")


if __name__ == "__main__":
    main()

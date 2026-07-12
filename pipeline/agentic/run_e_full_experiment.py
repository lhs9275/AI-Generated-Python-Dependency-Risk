"""
Workstream E full experiment runner.

Starts vLLM server (model_b), then runs all 4 conditions sequentially.
Writes per-condition JSONL manifests + summary JSON.

Usage (GPU required for vLLM):
  python -m pipeline.agentic.run_e_full_experiment \
    --model Qwen2.5-Coder-7B-Instruct \
    --bench bench \
    --n-per-family 10 \
    --port 8000 \
    --max-turns 10 \
    --out results/agentic
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.agentic.agent_harness import AgentHarness, CONDITION_TOOLS
from pipeline.agentic.run_agentic_tasks import select_tasks, append_to_manifest

import uuid

CONDITIONS = list(CONDITION_TOOLS.keys())
# agent_native_no_gate, agent_native_with_public_tests,
# agent_native_with_pip_dry_run, agent_with_guard_observation


def wait_for_vllm(base_url: str, timeout: int = 300, interval: int = 5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base_url}/models", timeout=3) as r:
                if r.status == 200:
                    print(f"[vllm] ready at {base_url}", flush=True)
                    return True
        except Exception:
            pass
        print(f"[vllm] waiting... ({int(deadline - time.time())}s left)", flush=True)
        time.sleep(interval)
    return False


def run_condition(
    tasks: list,
    condition: str,
    model_id: str,
    out_dir: Path,
    max_turns: int,
    seed: int,
    llm_base_url: str,
) -> list:
    manifests = []
    cond_dir = out_dir / condition
    cond_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cond_dir / "manifest.jsonl"

    for i, task_dir in enumerate(tasks, 1):
        run_id = uuid.uuid4().hex[:8]
        work_dir = cond_dir / task_dir.name / run_id
        print(
            f"  [{i}/{len(tasks)}] {task_dir.name} cond={condition} ...",
            end=" ", flush=True,
        )
        try:
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
            manifest["run_id"] = run_id
            manifest["condition"] = condition
            with open(manifest_path, "a") as f:
                f.write(json.dumps(manifest, default=str) + "\n")
            manifests.append(manifest)
            fm = manifest.get("failure_mode") or "ok"
            print(f"{fm} ({manifest.get('num_turns', 0)} turns)", flush=True)
        except Exception as exc:
            print(f"ERROR: {exc}", flush=True)
    return manifests


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--vllm-model", required=True, dest="model",
                   help="Model path (e.g. Qwen2.5-Coder-7B-Instruct)")
    p.add_argument("--bench", required=True)
    p.add_argument("--n-per-family", type=int, default=10)
    p.add_argument("--families", nargs="*")
    p.add_argument("--conditions", nargs="*", default=CONDITIONS)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--max-turns", type=int, default=10)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out", default="results/agentic")
    p.add_argument("--vllm-ready-timeout", type=int, default=300,
                   help="Seconds to wait for vLLM server to become ready")
    args = p.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    base_url = f"http://localhost:{args.port}/v1"

    # ── start vLLM ────────────────────────────────────────────────────────────
    vllm_cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", args.model,
        "--gpu-memory-utilization", "0.74",
        "--port", str(args.port),
    ]
    print(f"[vllm] starting: {' '.join(vllm_cmd)}", flush=True)
    vllm_proc = subprocess.Popen(
        vllm_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    if not wait_for_vllm(base_url, timeout=args.vllm_ready_timeout):
        vllm_proc.terminate()
        print("[vllm] ERROR: server did not become ready in time", file=sys.stderr)
        sys.exit(1)

    # ── select tasks ──────────────────────────────────────────────────────────
    tasks = select_tasks(
        Path(args.bench),
        n_per_family=args.n_per_family,
        families=args.families,
    )
    print(f"[exp] {len(tasks)} tasks × {len(args.conditions)} conditions", flush=True)

    # ── run conditions ────────────────────────────────────────────────────────
    summary = {}
    try:
        for cond in args.conditions:
            print(f"\n[exp] === condition: {cond} ===", flush=True)
            manifests = run_condition(
                tasks=tasks,
                condition=cond,
                model_id=args.model,
                out_dir=out_dir,
                max_turns=args.max_turns,
                seed=args.seed,
                llm_base_url=base_url,
            )
            ok = sum(1 for m in manifests if not m.get("failure_mode") or
                     m.get("failure_mode") in ("", "none"))
            summary[cond] = {"n": len(manifests), "ok": ok,
                             "failed": len(manifests) - ok}
            print(f"[exp] {cond}: {ok}/{len(manifests)} ok", flush=True)
    finally:
        print("\n[vllm] shutting down ...", flush=True)
        vllm_proc.terminate()
        try:
            vllm_proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            vllm_proc.kill()

    # ── write summary ─────────────────────────────────────────────────────────
    summary_path = out_dir / "e_experiment_summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "model": args.model,
            "n_per_family": args.n_per_family,
            "max_turns": args.max_turns,
            "seed": args.seed,
            "conditions": summary,
        }, f, indent=2)
    print(f"\n[exp] summary → {summary_path}")
    for cond, s in summary.items():
        print(f"  {cond}: {s['ok']}/{s['n']} ok")


if __name__ == "__main__":
    main()

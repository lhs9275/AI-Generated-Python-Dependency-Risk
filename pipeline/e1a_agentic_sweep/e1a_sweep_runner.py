#!/usr/bin/env python3
"""e1a_sweep_runner -- drain agentic-sweep rows for the served model. (E1a step 2/3)

Reads the unified sweep manifest and, for the model whose vLLM endpoint is
currently reachable, runs the EXISTING agentic harness
(pipeline/agentic/run_agentic_tasks.py) for each pending (condition, seed) row.
It does NOT serve vLLM itself (the wrap-a-server shell pattern is
forbidden); the server is launched separately on a GPU node and reached over
--endpoint. This runner is CPU/orchestration only (LLM work is remote), so it can
run on the login node while the GPU is held by the separate vLLM job.

Resumable: a row with a `.done` marker in its results-dir is skipped.

Cluster pattern (one model at a time, exclusive vLLM per user):
  # 7B (no quant)
  python -m vllm.entrypoints.openai.api_server \
    --model Qwen2.5-Coder-7B-Instruct \
    --gpu-memory-utilization 0.74 --port 8000
  # then, once it is up:
  python pipeline/e1a_agentic_sweep/e1a_sweep_runner.py \
    --sweep results/agentic_e1a/sweep.jsonl \
    --only-model Qwen2.5-Coder-7B-Instruct \
    --endpoint http://<vllm-host>:8000/v1
  # repeat per served model (14B/32B need --quantization awq_marlin)

Pure stdlib + subprocess.
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request

HARNESS = "pipeline/agentic/run_agentic_tasks.py"


def log(m):
    print(m, file=sys.stderr, flush=True)


def served_model(endpoint):
    """GET {endpoint}/models -> first model id, or None."""
    try:
        url = endpoint.rstrip("/") + "/models"
        with urllib.request.urlopen(url, timeout=10) as r:
            d = json.loads(r.read().decode())
        data = d.get("data") or []
        return data[0]["id"] if data else None
    except Exception as e:
        log(f"  endpoint probe failed: {e}")
        return None


def rows(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", default="results/agentic_e1a/sweep.jsonl")
    ap.add_argument("--endpoint", default="http://localhost:8000/v1")
    ap.add_argument("--only-model", default="", help="model path/tag to process (default: auto-detect from endpoint)")
    ap.add_argument("--bench", default="bench")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    target = args.only_model
    if not target:
        sid = served_model(args.endpoint)
        if not sid:
            log("no --only-model and endpoint not reachable; aborting.")
            sys.exit(2)
        target = sid
        log(f"auto-detected served model id: {sid}")

    def match(row):
        t = target.rstrip("/")
        return (row["model_path"].rstrip("/") == t or row["model_tag"] == t
                or os.path.basename(t) == os.path.basename(row["model_path"].rstrip("/"))
                or os.path.basename(t) == row["model_tag"])

    todo = [r for r in rows(args.sweep) if match(r)]
    if not todo:
        log(f"no sweep rows match target '{target}'. Check --only-model.")
        sys.exit(1)
    log(f"{len(todo)} rows for model '{target}'")

    ran = skipped = failed = 0
    for r in todo:
        rd = r["results_dir"]
        done = os.path.join(rd, ".done")
        if os.path.exists(done):
            skipped += 1
            continue
        os.makedirs(rd, exist_ok=True)
        cmd = [args.python, HARNESS,
               "--bench", args.bench,
               "--model", r["model_path"],
               "--condition", r["condition"],
               "--n-per-family", str(r["n_per_family"]),
               "--max-turns", str(r["max_turns"]),
               "--seed", str(r["seed"]),
               "--results-dir", rd,
               "--manifest-out", os.path.join(rd, "manifest.json"),
               "--llm-base-url", args.endpoint]
        log(f"  RUN {r['model_tag']} {r['condition']} s{r['seed']}")
        if args.dry_run:
            log("    " + " ".join(cmd))
            continue
        rc = subprocess.call(cmd)
        if rc == 0:
            open(done, "w").write("ok\n")
            ran += 1
        else:
            failed += 1
            log(f"    FAILED rc={rc}")
    log(f"done. ran={ran} skipped={skipped} failed={failed}")
    log("when ALL models drained -> python pipeline/e1a_agentic_sweep/e1a_aggregate.py")


if __name__ == "__main__":
    main()

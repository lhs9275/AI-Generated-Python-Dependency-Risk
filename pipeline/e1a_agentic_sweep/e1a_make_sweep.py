#!/usr/bin/env python3
"""e1a_make_sweep -- build the unified agentic-intervention sweep manifest. (E1a step 1/3)

Workstream E1a: re-run the paired controlled intervention (B0 vs B3, patch held
fixed) under an AGENTIC generation harness, so the causal mitigation result lives
on the agentic-generation mode that the naturalistic prevalence corpus is drawn
from (closing the disjoint single-pass-vs-agentic gap, and -- when the generators
are corpus tools driven over cluster models -- partially the generator-identity
gap).

This emits ONE unified JSONL (the cluster's preferred sweep format): one row per
(model, condition, seed) job unit. The runner (step 2) drains the rows for
whichever model's vLLM endpoint is currently served. Scoring + the paired B0/B3
gate are applied by the existing pipeline at aggregation (step 3).

Pure stdlib. No GPU here -- this just writes the manifest.

Example:
  python pipeline/e1a_agentic_sweep/e1a_make_sweep.py \
    --n-per-family 20 --seeds 0 1 --output results/agentic_e1a/sweep.jsonl
"""
import argparse
import json
import os
import re

DEFAULT_MODELS = [
    "Qwen2.5-Coder-7B-Instruct",
    "deepseek-coder-6.7b-instruct",
    "Qwen2.5-Coder-14B-Instruct-AWQ",
    "Qwen2.5-Coder-32B-Instruct-AWQ",
    "CodeLlama-7b-Instruct-hf",
]
# generation-side conditions (map to the paper's G0 / G1). The B0/B3 gate is a
# scoring-side variable applied later, NOT here.
DEFAULT_CONDITIONS = ["agent_native_no_gate", "agent_native_with_public_tests"]
# models that need AWQ marlin quantization when served (for the runbook hint)
AWQ = ("AWQ",)
HIGHMEM = ("32B",)


def tag(model_path):
    return re.sub(r"[^A-Za-z0-9.]+", "-", os.path.basename(model_path.rstrip("/"))).strip("-")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    ap.add_argument("--conditions", nargs="+", default=DEFAULT_CONDITIONS)
    ap.add_argument("--seeds", nargs="+", type=int, default=[0, 1])
    ap.add_argument("--n-per-family", type=int, default=20, help="20 x 6 families = 120 tasks")
    ap.add_argument("--max-turns", type=int, default=10)
    ap.add_argument("--results-root", default="results/agentic_e1a")
    ap.add_argument("--output", default="results/agentic_e1a/sweep.jsonl")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    n = 0
    with open(args.output, "w", encoding="utf-8") as fh:
        for m in args.models:
            mt = tag(m)
            for cond in args.conditions:
                for seed in args.seeds:
                    row = {
                        "model_path": m,
                        "model_tag": mt,
                        "condition": cond,
                        "seed": seed,
                        "n_per_family": args.n_per_family,
                        "max_turns": args.max_turns,
                        "results_dir": f"{args.results_root}/{mt}/{cond}__s{seed}",
                        "serve_hint": {
                            "quantization": "awq_marlin" if any(a in m for a in AWQ) else None,
                            "gpu_class": "high-vram" if any(h in m for h in HIGHMEM) else None,
                        },
                    }
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    n += 1
    print(f"wrote {n} job rows -> {args.output}")
    print(f"models={len(args.models)} conditions={len(args.conditions)} seeds={len(args.seeds)}")
    print("next: serve one model on a GPU node, then run e1a_sweep_runner.py --only-model <path>")


if __name__ == "__main__":
    main()

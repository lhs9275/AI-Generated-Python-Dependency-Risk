# E1a — Agentic-generation controlled intervention (unified JSONL sweep)

Re-runs the paired controlled intervention (**B0 vs B3, patch held fixed**) under the
existing **agentic** harness (`pipeline/agentic/run_agentic_tasks.py`, ReAct tool loop)
across all 5 models × generation conditions × seeds. Goal: show the single-pass
`RiskyAcc-Core 15.8–35.8% → 0.8–3.3%` reduction **holds under agentic generation** — the
mode the naturalistic prevalence corpus is in — closing the disjoint-generator objection
**causally** (E1b only does it observationally).

Orchestration only; it does **not** serve vLLM (the wrap-a-server pattern is forbidden).
The server is launched separately on a GPU node (one model at a time);
the runner reaches it over `--endpoint`.

## Scripts
- `e1a_make_sweep.py` — write the unified `sweep.jsonl` (one row per model×condition×seed).
- `e1a_sweep_runner.py` — drain the rows for the **currently-served** model (subprocesses the existing harness). Resumable (`.done` markers).
- `e1a_aggregate.py` — pool scored runs → `RiskyAcc-Core` B0 vs B3 per model/condition (Wilson CI) + paper table; compares to single-pass.

## Run order

```bash
# 1) build the sweep manifest (no GPU)
python pipeline/e1a_agentic_sweep/e1a_make_sweep.py \
  --seeds 0 1 --n-per-family 20 --output results/agentic_e1a/sweep.jsonl

# 2) PER MODEL (one at a time — exclusive vLLM per user):
#    serve it on a GPU node, then drain its rows.

#    7B / 6.7B (no quant)
python -m vllm.entrypoints.openai.api_server \
  --model Qwen2.5-Coder-7B-Instruct \
  --gpu-memory-utilization 0.74 --port 8000
#    14B AWQ
python -m vllm.entrypoints.openai.api_server \
  --model Qwen2.5-Coder-14B-Instruct-AWQ \
  --quantization awq_marlin --gpu-memory-utilization 0.74 --max-model-len 8192 --port 8000
#    32B AWQ
python -m vllm.entrypoints.openai.api_server \
  --model Qwen2.5-Coder-32B-Instruct-AWQ \
  --quantization awq_marlin --gpu-memory-utilization 0.74 --max-model-len 8192 --port 8000

#    once the chosen model is up (note its host:port), drain its rows
#    (CPU/orchestration job — LLM work is remote; can run on the login node):
python pipeline/e1a_agentic_sweep/e1a_sweep_runner.py \
  --sweep results/agentic_e1a/sweep.jsonl \
  --only-model Qwen2.5-Coder-7B-Instruct \
  --endpoint http://<vllm-host>:8000/v1
#    repeat for each of the 5 models (tear the server down between models)

# 3) aggregate once all models drained (+ score if not auto-scored)
python pipeline/e1a_agentic_sweep/e1a_aggregate.py \
  --sweep results/agentic_e1a/sweep.jsonl --score \
  --single-pass results/<single_pass_riskyacc_core>.csv \
  --out-dir results/agentic_e1a
```

## Outputs
- `e1a_riskyacc_core.csv`, `e1a_summary.json`, `e1a_table.tex` (`\label{tab:e1a}`):
  RiskyAcc-Core B0 vs B3 per model/condition, Δpp, Wilson CIs, single-pass comparison.

## Cluster-rule compliance
- vLLM served on a GPU node (one model at a time); the runner connects over `--endpoint`.
- One unified `sweep.jsonl` (manifest the runner iterates) — **not** N separate submissions.
- The runner is CPU/orchestration; the GPU is held only by the vLLM job.
- AWQ models: `--quantization awq_marlin`; 32B needs a high-VRAM GPU. `gpu-memory-utilization ≤ 0.74`.

## Stronger variant (generator-IDENTITY gap)
To also close the tool-identity gap, drive the real corpus agents that are scriptable —
`aider`, the `codex` CLI, `claude-code` — pointed at the same vLLM endpoint (they are
OpenAI-compatible clients), wrapping each per task instead of the built-in ReAct loop.
Honest limit: these run over **open-weight cluster backends**, not the agents' real
commercial backends, so backend-model identity stays unobserved. Still closes generation
mode + tool scaffold.

## Cost
GPU-heavy (5 models × 2 conditions × 2 seeds × 120 tasks × ~10 turns). Sequential per model
due to the one-server-per-user rule. Days. Revision-cycle, not pre-submission.

## Honest scope to state in the paper
Closes the **generation-mode** gap (single-pass → agentic) fully, and the **tool-identity**
gap partially (if corpus agents are used). The agents' commercial backend models remain
unobserved; this is "agentic generation on open-weight backends," not exact commercial
reproduction.

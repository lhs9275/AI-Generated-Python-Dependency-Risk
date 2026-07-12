# E1a upgrade — U2 (independent oracle) + U3 (naturalistic-grounded tasks)

Makes the agentic intervention attack the BIG reject driver (co-design circularity) that
plain E1a leaves open, without the cost of U1 (real commercial backends, skipped).

- **U3**: tasks are built from REAL agent-authored risky PRs, not the co-designed
  benchmark → gate-independent task population, on the prevalence population.
- **U2**: a generated change is labeled risky by a LIVE OSV/PyPI oracle, not the authors'
  `risk_oracle.yaml` → "gate catches its own oracle" removed at the scoring layer.
- Generation stays on open-weight cluster models (U1 skipped) → backend-identity gap and
  single-ecosystem stay open (honest residual).

Scope: VERSION risk (P2 invalid pin / P3 vulnerable pin) — the package name is given, the
agent freely picks the version; the live oracle judges it. P1 hallucination replay needs
the original PR goal text (absent) → future work.

## Flow
```bash
# (labels already exist: results/tse_gap_closure/data/labels_A.csv ; P3 267 / P2 49 / P1 24)

# U3) build PR-grounded tasks (313 risky P2/P3 + matched safe controls)
python pipeline/e1a_agentic_sweep/e1a_tasks_from_prs.py \
  --patches results/tse_gap_closure/data/dependency_change_patches.jsonl \
  --labels  results/tse_gap_closure/data/labels_A.csv \
  --output  results/e1a_pr_tasks/tasks.jsonl

# generate: per served vLLM model (one at a time), two conditions (G0/G1 analog)
python -m vllm.entrypoints.openai.api_server \
  --model Qwen2.5-Coder-7B-Instruct --gpu-memory-utilization 0.74 --port 8000
python pipeline/e1a_agentic_sweep/e1a_run_pr_tasks.py \
  --tasks results/e1a_pr_tasks/tasks.jsonl \
  --model Qwen2.5-Coder-7B-Instruct --tag qwen7b \
  --condition agent_native --endpoint http://<host>:8000/v1
#   repeat with --condition safety_prompt and for each model

# gate the generated changes with the EXISTING ladder (reused, unchanged)
python pipeline/tse_gap_closure/run_gate_ladder.py \
  --patches results/e1a_pr_gen/qwen7b/agent_native/generated_changes.jsonl \
  --out     results/e1a_pr_gen/qwen7b/agent_native/guard_outputs.jsonl

# U2) independent live-OSV/PyPI oracle + RiskyAcc-Core B0 vs B3 + McNemar + false-block
python pipeline/e1a_agentic_sweep/e1a_score_independent.py \
  --generated results/e1a_pr_gen/qwen7b/agent_native/generated_changes.jsonl \
  --gate      results/e1a_pr_gen/qwen7b/agent_native/guard_outputs.jsonl \
  --out-dir   results/e1a_pr_gen/qwen7b/agent_native
```

## Outputs
`e1a_independent_summary.json`, `e1a_independent_table.tex` (`\label{tab:e1a-indep}`):
RiskyAcc-Core B0 vs B3 (Wilson CI) over independent-oracle-risky generated changes,
paired McNemar (b,c,p), and B3 false-block on safe controls.

## What this buys (cold)
Closes generation-mode + breaks co-design circularity (task + oracle both gate-independent),
on the prevalence population. P(reject) lever: ~0.40 → ~0.30 combined with E2.

## Honest residual (state in paper)
- U1 skipped: open-weight backends, not the agents' commercial backends → backend identity unobserved.
- Single ecosystem (PyPI) → E3 (npm) still open.
- Version-risk only (P2/P3); P1 hallucination replay = future work.
- Frontier-agent non-determinism N/A here (cluster models, fixed temperature, seeded).
- Subset / CI width: report n and Wilson/McNemar honestly; don't over-read small cells.

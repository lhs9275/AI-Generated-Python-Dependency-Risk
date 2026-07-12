# E1b — Real-World Exposure Linkage

Links the prevalence study (deployed-agent PRs) to the gate's BLOCK decisions on the
**same population**, to answer the reviewer objection that prevalence and the controlled
intervention are measured on **disjoint generator sets**.

**Claim it supports (observational):** the gate's BLOCK set corresponds to PRs that
actually merged and whose risk actually materialized — preventable real-world exposure on
the prevalence population. **Not** a causal merge-rate effect (the gate never acted on
these PRs). State this caveat in the paper.

## Inputs already in the repo
- patches: `results/tse_gap_closure/data/dependency_change_patches.jsonl` (change_id, pr_url, package, version, created_at)
- labels:  produced by `pipeline/tse_gap_closure/label_A.py` (change_id, label_primary = P1/P2/P3)
- gate:    produced by `pipeline/tse_gap_closure/run_gate_ladder.py` → `guard_outputs.jsonl` (change_id, decisions{B3})

## Run order (CPU/network only — no GPU; run from your own dir)

```bash
# 0) token (do NOT commit, do NOT pass on argv)
export GITHUB_TOKEN=ghp_xxx

# 1) guard-independent labels (if not already produced) -> CSV with change_id,label_primary
python pipeline/tse_gap_closure/label_A.py \
  --evidence data/real_pr_routine/historical_evidence.jsonl \
  --out results/e1b_exposure/labels_A.csv

# 2) gate decisions per change (frozen PR-time evidence)
python pipeline/tse_gap_closure/run_gate_ladder.py \
  --patches results/tse_gap_closure/data/dependency_change_patches.jsonl \
  --out results/e1b_exposure/guard_outputs.jsonl

# 3) NEW: real-world PR merge outcomes (GitHub API; resumable)
python pipeline/e1b_exposure/e1b_collect_merge.py \
  --input results/tse_gap_closure/data/dependency_change_patches.jsonl \
  --output results/e1b_exposure/pr_outcomes.jsonl
# smoke first: add --limit 20

# 4) NEW: did the risk materialize? (current PyPI/OSV; resumable, cached)
python pipeline/e1b_exposure/e1b_materialize_risk.py \
  --patches results/tse_gap_closure/data/dependency_change_patches.jsonl \
  --labels  results/e1b_exposure/labels_A.csv \
  --output  results/e1b_exposure/risk_realized.jsonl

# 5) NEW: join + crosstab + paper table
python pipeline/e1b_exposure/e1b_linkage.py \
  --patches  results/tse_gap_closure/data/dependency_change_patches.jsonl \
  --labels   results/e1b_exposure/labels_A.csv \
  --gate     results/e1b_exposure/guard_outputs.jsonl \
  --outcomes results/e1b_exposure/pr_outcomes.jsonl \
  --realized results/e1b_exposure/risk_realized.jsonl \
  --out-dir  results/e1b_exposure
```

## Outputs
- `linkage_summary.json` — merge-rate (risky vs safe, Wilson CI), 3-way crosstab
  (B3 × merged × materialized), **preventable-exposure** headline, P3 lead-time / silent floor.
- `linkage_table.tex` — paper-ready Table (`\label{tab:exposure}`).
- `linkage_rows.csv` — per-change audit trail.

## Headline metric
**Preventable exposure** = primary-risky changes where `B3=BLOCK ∧ PR merged ∧ risk materialized`.
These are real supply-chain entries on the prevalence population that the gate would have
flagged at PR time — the bridge from prevalence to the gate.

## Threats to state
- Observational (no counterfactual of "what if blocked"): report exposure, not merge-rate reduction.
- `merged ≠ deployed`: use the `--star-tier` repo breakdown to separate non-toy repos.
- Outcome uses CURRENT evidence while the gate uses FROZEN PR-time evidence (intended temporal split).
- Coverage: closed/deleted PRs and private repos return `unknown`; report join coverage from the summary.

## Notes
- All three E1b scripts are pure-stdlib and resumable (re-run continues from cache).
- GitHub auth: ~1,100 unique PRs ≈ a few minutes at 5,000 req/h authenticated.

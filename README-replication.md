# AgentSupplyGuard — Replication Package

This package accompanies the paper:
> *AI-Generated Python Dependency Risk: Naturalistic Prevalence, Enforcement Limits, and a Controlled Detectability Benchmark*
> — Hyeonsu Lee and Geunseok Yang, Department of Computer Science and Applied Mathematics, Hankyong National University.

This artifact supports verification of all reported tables and statistical claims without regenerating model outputs. GPU execution is required only to reproduce the original LLM generations. The main verification path starts from archived per-run JSON files, audits the frozen S1 package-existence evidence, recomputes strict-offline guard decisions into `results/offline_v2/canonical_runs.jsonl`, and then derives the paper tables from that JSONL.

---

## Contents

```
AgentSupplyGuard_artifact/
├── README-replication.md     Reproduction entry point (this file; also covers
│                             artifact structure, reproducibility checklist, upload steps)
├── bench/                    120 tasks (F1–F6), evidence_refs, risk_oracle, tests_hidden
├── pipeline/                 Guard implementation + analysis scripts
│   ├── guard/                S1–S6 stage implementations (run_guard entry: guard/decision.py)
│   ├── run_pipeline.py       CLI driver: generate + score one/family/all tasks (GPU)
│   ├── run_task.py           Per-task library called by run_pipeline.py (no standalone CLI)
│   ├── reproduce_tables.py   Re-derive manuscript tables/claims from strict-offline JSONL
│   ├── recompute_offline_guard_results.py  Recompute B0/B1/B2/B3/ablation modes
│   │                                      from frozen evidence with no live PyPI calls
│   ├── build_tables.py       Render Tables to Markdown from per-run result.json
│   ├── compute_tse_stats.py  McNemar / Cohen's h / odds ratios (RQ3 stats)
│   ├── build_figures.py      Reproduce Figures 1–4
│   ├── retroactive_scan.py   Disabled historical batch scanner (see validity notice)
│   ├── aidev_evaluate.py     Retroactive B3 guard on real AIDev PRs (no GPU)
│   ├── aidev_stratify.py     AIDev stratification re-analysis
│   └── agent_workflow.py     Multi-step ReAct workflow auxiliary study (§4.3)
├── scripts/                  Final-audit consistency and anonymity checks
├── results/
│   ├── *.json                Aggregated results (cumulative, tse_stats, aidev v4, seed_variance,
│   │                         independent_detection, workflow_pilot_summary)
│   ├── metrics_v2/           AFSP accept-denominator, RiskyAcc variants
│   ├── offline_v2/           Strict-offline canonical_runs.jsonl + decision deltas
│   ├── evidence_coverage/    S1 snapshot coverage audit and PyPI backfill facts
│   ├── external_realrisk_py/ External risk-containing recall corpus (107 cases)
│   └── task_*/…/result.json  Every per-run result.json (raw task-level outputs;
│                             heavy venv/ and repo/ working dirs pruned from the archive)
├── evaluation/manual_audit/  Manual audit sheets, rating rubric/guide, IRR script + report
├── outputs/reproduce_logs/   Frozen reproducibility run logs (all exit 0) + manifest
├── references_audit.md       Reference coverage audit
├── LICENSE                   MIT (code) + CC BY 4.0 (benchmark data)
└── requirements.txt          Python dependencies
```

> The manuscript source is **not** bundled here; it is submitted separately
> through the journal system. Archive integrity is guaranteed by the DOI
> record; the manuscript pins no SHA-256 hash.

---

## Requirements

- Python 3.10+
- vLLM ≥ 0.4 (for LLM inference; GPU required)
- See `requirements.txt` for analysis-only dependencies

```bash
pip install -r requirements.txt
```

> **Reproduction vehicle.** Core-table reproduction (Step 1) reads the per-run
> `results/task_*/…/result.json` files, verifies that every canonical S1 package
> decision has frozen snapshot evidence, recomputes guard outcomes into
> `results/offline_v2/canonical_runs.jsonl`, and then reads that JSONL for the
> table and claim checks. All 3,300 per-run `result.json` files and
> `canonical_runs.jsonl` are git-tracked, so a bare `git clone` reproduces every
> headline table offline with no ZIP required. The only omitted file is one
> oversized regeneration cache (`results/e1a_pr_gen/_indep_cache.json`, ~166 MB,
> exceeds GitHub's per-file limit), which no reproduction script reads.

---

## Reproducing the Main Results

All of Steps 1–4 run from the shipped `results/task_*/…/result.json` files and
need **no GPU**. Step 5 regenerates patches and requires a GPU.

> **Quick check.** The sole core strict-offline verification path is
> `scripts/reproduce_tables.sh`; it runs offline from the repo root and exits
> with status 0 on success. Logs are not pre-shipped; re-run it to regenerate
> its log deterministically. See `outputs/reproduce_logs/README.md` for the
> script→check mapping.

### Step 1 — Verify all tables and manuscript claims (no GPU needed)

```bash
./scripts/reproduce_tables.sh
```

This one-command path runs the S1 evidence-coverage audit, recomputes
`results/offline_v2/canonical_runs.jsonl` from frozen evidence, re-derives
Tables 2–4, the manuscript odds-ratio / confidence-interval claims, ablation deltas,
paired McNemar checks, primary Holm checks with `n_pairs=120/model`, sensitivity
analysis, and a socket-denied no-network gate. It prints
`✓ All values consistent with manuscript` and writes
`results/statistical_consistency_check.md`.

The npm cross-ecosystem replication (Table VIII: prevalence 4.83%, ported-gate
block recall, npm-audit baseline) is reproduced from the archived
`results/npm_*.json` via `pipeline/npm_prevalence_robust.py` (prevalence + strict
temporal grade + F1/F2/F3 mix) and `pipeline/npm_external_recall.py` (external
recall corpus, block recall, npm-audit analogue); no GPU or network required.

To render the tables as Markdown:

```bash
python pipeline/build_tables.py --results-dir results/ --bench-root bench/ \
    --aidev-eval results/aidev_evaluation_v4.json
```

### Step 2 — Reproduce statistical tests (no GPU needed)

```bash
python -m pipeline.compute_tse_stats \
    --runs-jsonl results/offline_v2/canonical_runs.jsonl
# Writes results/tse_stats.json and results/tse_tables.tex
# (paired McNemar exact p, Cohen's h, Haldane-Anscombe odds ratios for RQ3)
```

### Step 3 — Reproduce figures (no GPU needed)

```bash
python pipeline/build_figures.py --results-dir results/
# Output: research_notes/figures/fig{1,2,3,4}.{pdf,png}
```

### Step 4 — Retroactive guard on real AIDev PRs (no GPU needed)

```bash
python pipeline/aidev_stratify.py \
    --sample results/aidev_sample_v2.jsonl \
    --eval results/aidev_evaluation_v4.json \
    --out-csv results/aidev_stratification.csv \
    --out-md results/aidev_stratification_summary.md

python pipeline/aidev_stratify.py \
    --sample results/aidev_sample_scaleup.jsonl \
    --eval results/aidev_evaluation_scaleup.json \
    --out-csv results/aidev_stratification_scaleup.csv \
    --out-md results/aidev_stratification_scaleup_summary.md

python scripts/check_aidev_overlap.py
```

Re-runs the B3 guard over the frozen AIDev dependency-change PR sample and
reproduces the external-validation counts (0 primary-signal PRs, license-gap
flags, true negatives).

### Step 4b — Final submission consistency checks (no GPU needed)

```bash
python scripts/check_table6c_monotonicity.py
python pipeline/independent_detection.py --frozen
```

`check_table6c_monotonicity.py` writes `results/table6c_monotonicity_summary.json`,
`results/table6c_falseblock_monotonicity_check.csv`, and
`results/violations_falseblock_monotonicity.csv`.

### Step 5 — Full end-to-end re-run (GPU required)

`run_task.py` is a library (no standalone CLI); the driver is `run_pipeline.py`,
which reads model definitions from `pipeline/config.py` (`model_a`…`model_e`).
Start a vLLM server on `localhost:8000`, then:

```bash
# One task, Qwen-7B (model_b), G0 condition
python pipeline/run_pipeline.py --task F1_package_existence/task_F1_001 \
    --model model_b --cond G0

# A whole family, both conditions
python pipeline/run_pipeline.py --family F1_package_existence \
    --model model_b --all-conditions

# Full corpus: all tasks × all models × G0/G1
python pipeline/run_pipeline.py --all --all-models --all-conditions
```

---

## Benchmark Structure (per task)

```
task_FX_NNN/
├── prompt.md              Natural-language coding task
├── evidence_refs.json     PR-time public evidence (registry, CVE, license)
├── dependency_policy.yaml Organisation dependency policy
├── risk_oracle.yaml       Ground-truth risk labels (S1–S6)
├── repo/                  Minimal Python repo skeleton
├── tests_public/          Functional tests (visible to agent)
└── tests_hidden/          Functional + safety oracle tests
```

---

## Guard Modes

| Mode | Description |
|---|---|
| B0 | No guard (baseline) |
| B1_deterministic | Existence + CVE check (S1+S3, evidence_refs only) |
| B1_scanner | Historical controlled pip-audit batch; invalid and excluded (see `results/scanner_baseline_matrix/VALIDITY_NOTICE.md`) |
| B2_deterministic | B1_det + license check (S4) |
| B2_scanner | Historical controlled pip-audit batch + license check; invalid and excluded |
| B3 | Full guard (S1–S6) |
| R1 | B3 + one-shot repair loop |

---

## Statistical Tests

```bash
# Strict RQ3 reproduction (writes results/tse_stats.json and results/tse_tables.tex)
python -m pipeline.compute_tse_stats --runs-jsonl results/offline_v2/canonical_runs.jsonl

# Optional legacy proxy checks only; this does not regenerate the strict TSE artifacts.
bash scripts/verify_legacy_proxy.sh
```

---

## Manual Audit & Inter-Rater Material (§7.1)

The blind manual audit of F4/F6 patches and the agreement analysis live under
`evaluation/manual_audit/`:

```bash
python evaluation/manual_audit/compute_irr.py   # agreement report → irr_report.md
```

Rating sheets (`rating_sheet_rater*.csv`, `results.csv`), the sampling
metadata (`sample_meta.json`), and the rubric/guide (`RATING_RUBRIC.md`,
`RATING_GUIDE.md`) are included so the audit is fully inspectable. Note the
manuscript reports a single-annotator oracle-agreement audit (§7.1); the
material here documents that procedure.

---

## Multi-Step Agent Workflow Auxiliary Study (§4.3, §7.2)

The ReAct workflow pilot (240 runs, 2 arms) is reproducible via:

```bash
# GPU-free harness validation with a scripted policy
python pipeline/agent_workflow.py --input <runs>.jsonl --output results/workflow_pilot/ --mock

# Real run (GPU; vLLM server on localhost:8000)
python pipeline/agent_workflow.py --input <runs>.jsonl --output results/workflow_pilot/
```

Each input JSONL row is `{"task_dir": ..., "model_id": ..., "arm": "workflow"|"workflow_guard"}`.
Aggregated results are in `results/workflow_pilot_summary.json`.

---

## Reproducibility Checklist

Generated: 2026-07-06

### Environment

| Item | Value |
|---|---|
| Python | 3.10+ (conda env: see artifact README) |
| GPU | Not required for reproduction scripts; only for regenerating model outputs |
| Random seed | All generations: temperature=0.2, seed per model (fixed in artifact) |
| Qwen-7B 3-seed | seeds 42, 123, 7 (`results/seed_variance.json`) |

### Strict-offline core verification (written and verified, exit 0)

```bash
./scripts/reproduce_tables.sh       # strict-offline audit/recompute + all tables/statistics + no-network gate
```

### Supplemental checks

```bash
./scripts/run_guard_on_examples.sh  # S1/S2/S3 BLOCK demo on frozen snapshots (verified)
./scripts/check_no_network_repro.sh # socket-denied strict-offline replay check (PASS)
./scripts/check_no_oracle_leakage.sh  # guard/adjudicator code separation check (PASS)
```

Each script wraps `pipeline/` modules:
- `reproduce_tables.sh` → `audit_evidence_coverage`, `recompute_offline_guard_results`, `reproduce_tables`, `mcnemar_v2`, `compute_primary_mcnemar --expect-core-pairs 120`, `sensitivity_analysis`, `check_no_network_repro`
- `run_guard_on_examples.sh` → `run_guard_on_examples` (frozen `evidence_refs`/`dependency_policy` only, no network/oracle)
- `check_no_oracle_leakage.sh` → confirms `guard/` never references `risk_oracle`/`adjudicator`, and `adjudicator/` never imports `guard`

Optional non-manuscript legacy check: `scripts/verify_legacy_proxy.sh` recomputes
the pre-strict raw-result expanded-proxy ladder. It is not a strict-offline
reproduction and is not part of the core reviewer path.

### Oracle leakage check

`guard` (reads `evidence_refs.json`) and `adjudicator` (reads `risk_oracle.yaml`) share no code path.
Verify: `grep -r "risk_oracle" pipeline/guard/` → 0 hits.

### Verification status

| Item | Status |
|---|---|
| Table 3 RiskyAcc-Core numbers | Re-aggregated and verified (25.8→1.7 etc. match prose) |
| McNemar p, Cohen's h, OR | Cross-checked via `reproduce_tables.py` |
| External recall corpus (107 cases) | Confirmed present in `results/external_realrisk_py/` |
| AIDev 72 cases (v4) | Confirmed present in `results/aidev_evaluation_v4.json` |
| SafetyPass holistic vs Core (F1/F2/F3) | Done — `recompute_safetypass_core.py`; holistic 74.8% / Core(F123) 91.2% pooled (`results/safetypass_core_recompute.json`) |
| B1_resolver / B1_osv / B2_practical baseline | Done — stage-subset proxy; `additional_baselines.csv` (Table 4b) |
| Strict-offline S1 evidence coverage | Done — `pipeline.audit_evidence_coverage --fail-on-missing`; 0 missing canonical S1 packages after backfill |
| No-network reproduction gate | Done — `scripts/check_no_network_repro.sh` denies sockets and re-runs strict-offline replay checks |
| `scripts/reproduce_*.sh` | Done — scripts written and run-verified (exit 0) |
| Zenodo DOI | TODO (added at camera-ready — human action) |

### Random seed log

| Model | Seed | Condition |
|---|---|---|
| Qwen2.5-Coder-7B | 42 (canonical), 123, 7 | G0+G1, full |
| Qwen2.5-Coder-14B-AWQ | 42 | G0+G1 |
| Qwen2.5-Coder-32B-AWQ | 42 | G0+G1 |
| DeepSeek-Coder-6.7B | 42 | G0+G1 |
| CodeLlama-7b | 42 (canonical), 2nd seed | G0+G1 |

All vLLM generation: `temperature=0.2`, `max_model_len=8192`; the random seed for each run is recorded in the artifact's per-run JSON.

---

## Artifact Distribution

Submission is **single-anonymous** (TSE default): author identity is shown to
reviewers, so the artifact carries real author/affiliation information and no
anonymization is required.

**Review distribution (now).** The artifact is hosted as a public Git
repository, frozen at a submission tag so reviewers see the exact reviewed
state:

- Repository: <https://github.com/lhs9275/AI-Generated-Python-Dependency-Risk>
- Frozen tag: `tse-submission-2026-07-r5`
- Reviewer path: `git clone` → `cd` into the repo → `./scripts/reproduce_tables.sh`
  (no GPU, no network; verified exit 0).

**Excluded from the GitHub distribution.** One regeneration cache exceeds
GitHub's 100 MB per-file limit and is therefore omitted:

- `results/e1a_pr_gen/_indep_cache.json` (~166 MB) — a raw independent-scoring
  cache for the secondary frontier-model generation study (`e1a`). It is **not
  read by any reproduction script** (`reproduce_tables.sh` and the other
  `scripts/*.sh` derive every headline table from `bench/*/evidence_refs.json`,
  the per-run `result.json` files, and `results/offline_v2/canonical_runs.jsonl`).
  Excluding it does not affect any reported table, statistic, or figure; it is
  regenerated only when re-running the GPU frontier generation in Step 5.

**Permanent archive (camera-ready).** For a citable DOI, cut a GitHub release
from the submission tag and let **Zenodo** archive that release automatically
(GitHub → Zenodo integration), or upload the full package (including the
excluded cache) to Zenodo directly:

1. License matches `LICENSE` (MIT for code, CC BY 4.0 for data).
2. Copy the resulting **DOI** into the manuscript data-availability section at
   camera-ready.
3. The manuscript does **not** pin a SHA-256 (byte-fragility / rebuild-mismatch
   risk); archive integrity is guaranteed by the DOI record (Zenodo computes
   per-file checksums on upload).

Do not use a placeholder URL in the submitted manuscript.

---

## Contact

Geunseok Yang (corresponding author), Department of Computer Science and
Applied Mathematics, Hankyong National University — gsyang@hknu.ac.kr.
Hyeonsu Lee — lhs9275@hknu.ac.kr.

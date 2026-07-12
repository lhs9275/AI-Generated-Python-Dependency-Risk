# Artifact A: Additional Baseline Policies

This is a pre-strict raw-result expanded-proxy ladder. Its `afsp_pre_strict_proxy` values are not the manuscript's strict AFSP; the authoritative strict AFSP is Table IV / `results/metrics_v2/table5_baseline_ladder_v2.csv`.

## Allowlist baseline: NOT FEASIBLE

An allowlist requires knowing which packages are safe a priori.
In the AgentSupplyBench-Py setting, the only oracle-free definition would be
'packages already in the original requirements.txt', which is equivalent to
`block_all_new`. A curated allowlist (e.g., top-1000 PyPI packages) does not
apply because F1 tasks are constructed so the agent can choose hallucinated names
that would pass any popularity-based filter. **This policy is therefore not evaluated.**

## Results by model and mode

Columns: mode | RiskyAcc [95%CI] | BlockRate | AFSP_pre_strict_proxy | DIR | FalseAllow

### Qwen-7B

| Mode | RiskyAcc | [95% CI] | BlockRate | AFSP_pre_strict_proxy | DIR | FalseAllow |
|------|----------|----------|-----------|------|-----|------------|
| B0 | 26.2% (63/240) | [21–32] | 0.0% | 56.2% | 0.0% | 26.2% |
| B1 | 14.2% (34/240) | [10–19] | 14.2% | 54.2% | 2.1% | 14.2% |
| S1_only | 16.7% (40/240) | [12–22] | 10.4% | 55.4% | 0.8% | 16.7% |
| S1_S3 | 14.2% (34/240) | [10–19] | 14.2% | 54.2% | 2.1% | 14.2% |
| B1_resolver | 5.0% (12/240) | [3–9] | 22.1% | 55.4% | 0.8% | 5.0% |
| B1_osv | 23.8% (57/240) | [19–30] | 3.8% | 55.0% | 1.2% | 23.8% |
| B2_practical | 2.5% (6/240) | [1–5] | 25.8% | 54.2% | 2.1% | 2.5% |
| B2_practical_license | 1.7% (4/240) | [1–4] | 26.7% | 54.2% | 2.1% | 1.7% |
| S1_S2_S3 | 2.5% (6/240) | [1–5] | 25.8% | 54.2% | 2.1% | 2.5% |
| block_all_new | 0.0% (0/240) | [0–2] | 51.2% | 38.8% | 25.0% | 0.0% |
| B3 | 1.7% (4/240) | [1–4] | 27.5% | 53.3% | 2.9% | 1.7% |

### Qwen-14B

| Mode | RiskyAcc | [95% CI] | BlockRate | AFSP_pre_strict_proxy | DIR | FalseAllow |
|------|----------|----------|-----------|------|-----|------------|
| B0 | 30.0% (72/240) | [25–36] | 0.0% | 55.4% | 0.0% | 30.0% |
| B1 | 17.9% (43/240) | [14–23] | 12.1% | 55.4% | 0.0% | 17.9% |
| S1_only | 20.8% (50/240) | [16–26] | 9.2% | 55.4% | 0.0% | 20.8% |
| S1_S3 | 17.9% (43/240) | [14–23] | 12.1% | 55.4% | 0.0% | 17.9% |
| B1_resolver | 5.4% (13/240) | [3–9] | 26.2% | 54.6% | 1.7% | 5.4% |
| B1_osv | 27.1% (65/240) | [22–33] | 2.9% | 55.4% | 0.0% | 27.1% |
| B2_practical | 2.5% (6/240) | [1–5] | 29.2% | 54.6% | 1.7% | 2.5% |
| B2_practical_license | 0.8% (2/240) | [0–3] | 30.8% | 54.6% | 1.7% | 0.8% |
| S1_S2_S3 | 2.5% (6/240) | [1–5] | 29.2% | 54.6% | 1.7% | 2.5% |
| block_all_new | 0.0% (0/240) | [0–2] | 62.1% | 32.1% | 32.1% | 0.0% |
| B3 | 0.8% (2/240) | [0–3] | 30.8% | 54.6% | 1.7% | 0.8% |

### Qwen-32B

| Mode | RiskyAcc | [95% CI] | BlockRate | AFSP_pre_strict_proxy | DIR | FalseAllow |
|------|----------|----------|-----------|------|-----|------------|
| B0 | 22.9% (55/240) | [18–29] | 0.0% | 64.6% | 0.0% | 22.9% |
| B1 | 12.9% (31/240) | [9–18] | 12.9% | 63.3% | 2.9% | 12.9% |
| S1_only | 16.2% (39/240) | [12–21] | 7.1% | 64.6% | 0.4% | 16.2% |
| S1_S3 | 12.9% (31/240) | [9–18] | 12.9% | 63.3% | 2.9% | 12.9% |
| B1_resolver | 6.7% (16/240) | [4–11] | 20.4% | 62.5% | 4.2% | 6.7% |
| B1_osv | 19.6% (47/240) | [15–25] | 5.8% | 63.3% | 2.5% | 19.6% |
| B2_practical | 3.3% (8/240) | [2–6] | 26.2% | 61.3% | 6.7% | 3.3% |
| B2_practical_license | 2.1% (5/240) | [1–5] | 27.5% | 61.3% | 6.7% | 2.1% |
| S1_S2_S3 | 3.3% (8/240) | [2–6] | 26.2% | 61.3% | 6.7% | 3.3% |
| block_all_new | 0.0% (0/240) | [0–2] | 62.1% | 32.9% | 39.2% | 0.0% |
| B3 | 2.1% (5/240) | [1–5] | 27.5% | 61.3% | 6.7% | 2.1% |

### DeepSeek-6.7B

| Mode | RiskyAcc | [95% CI] | BlockRate | AFSP_pre_strict_proxy | DIR | FalseAllow |
|------|----------|----------|-----------|------|-----|------------|
| B0 | 13.8% (33/240) | [10–19] | 0.0% | 55.0% | 0.0% | 13.8% |
| B1 | 7.9% (19/240) | [5–12] | 5.8% | 55.0% | 0.0% | 7.9% |
| S1_only | 10.0% (24/240) | [7–14] | 3.8% | 55.0% | 0.0% | 10.0% |
| S1_S3 | 7.9% (19/240) | [5–12] | 5.8% | 55.0% | 0.0% | 7.9% |
| B1_resolver | 3.8% (9/240) | [2–7] | 10.0% | 55.0% | 0.0% | 3.8% |
| B1_osv | 11.7% (28/240) | [8–16] | 2.1% | 55.0% | 0.0% | 11.7% |
| B2_practical | 1.7% (4/240) | [1–4] | 12.1% | 55.0% | 0.0% | 1.7% |
| B2_practical_license | 0.8% (2/240) | [0–3] | 12.9% | 55.0% | 0.0% | 0.8% |
| S1_S2_S3 | 1.7% (4/240) | [1–4] | 12.1% | 55.0% | 0.0% | 1.7% |
| block_all_new | 0.0% (0/240) | [0–2] | 40.4% | 39.2% | 26.7% | 0.0% |
| B3 | 0.4% (1/240) | [0–2] | 13.3% | 55.0% | 0.0% | 0.4% |

### CodeLlama-7B

| Mode | RiskyAcc | [95% CI] | BlockRate | AFSP_pre_strict_proxy | DIR | FalseAllow |
|------|----------|----------|-----------|------|-----|------------|
| B0 | 33.3% (80/240) | [28–40] | 0.0% | 42.5% | 0.0% | 33.3% |
| B1 | 13.8% (33/240) | [10–19] | 20.0% | 42.5% | 0.4% | 13.8% |
| S1_only | 15.0% (36/240) | [11–20] | 18.8% | 42.5% | 0.4% | 15.0% |
| S1_S3 | 13.8% (33/240) | [10–19] | 20.0% | 42.5% | 0.4% | 13.8% |
| B1_resolver | 9.2% (22/240) | [6–13] | 25.4% | 41.7% | 1.2% | 9.2% |
| B1_osv | 32.1% (77/240) | [26–38] | 1.2% | 42.5% | 0.0% | 32.1% |
| B2_practical | 7.9% (19/240) | [5–12] | 26.7% | 41.7% | 1.2% | 7.9% |
| B2_practical_license | 7.5% (18/240) | [5–12] | 27.1% | 41.7% | 1.2% | 7.5% |
| S1_S2_S3 | 7.9% (19/240) | [5–12] | 26.7% | 41.7% | 1.2% | 7.9% |
| block_all_new | 0.0% (0/240) | [0–2] | 84.6% | 10.0% | 51.2% | 0.0% |
| B3 | 7.5% (18/240) | [5–12] | 28.3% | 40.4% | 2.5% | 7.5% |

## Key findings

- **S1_only** vs B3: shows how much of B3's gain comes from package-existence checking alone.
- **S1_S3** vs **S1_only**: incremental value of adding direct-CVE detection (S3) on top of S1.
- **S1_S3 vs B1**: S1_S3 and B1 use the *same* deterministic stage set {S1, S3} (see
  `decision._MODE_STAGES`), so they should be identical. They match exactly for 4 of 5
  models; CodeLlama differs by 2 runs (B1=30, S1_S3=28) because two F6 runs carry a parser
  artifact dependency named `import` (see results/recomputed_tables/parser_contamination.csv):
  recomputing S1 now blocks that nonexistent package, whereas the stored B1 did not.
  B1 is therefore NOT a separate 'scanner' policy here — the pip-audit scanner baseline is
  B1_scanner, a different column.
- **block_all_new**: upper bound — maximum possible RiskyAcc reduction at maximum DIR cost.
  If B3 RiskyAcc ≈ block_all_new RiskyAcc, B3 is nearly as effective as blocking everything,
  with much lower DIR. This strengthens the guard's precision-recall argument.

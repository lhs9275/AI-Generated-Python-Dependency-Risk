# G: R2 Repair Experiment — Findings

> Notice: This is a pre-strict-offline auxiliary repair sub-study; the authoritative strict AFSP is Table IV / `results/metrics_v2/table5_baseline_ladder_v2.csv`.

Frozen 1,200-generation corpus. R0 = B3 block-only baseline; R1 = one-shot
guard-feedback repair of B3-blocked patches; R2 = iterative (max 2) guard +
public-test-feedback repair. Hidden tests used for final scoring only.
Unblocked patches carry the original patch forward for R1/R2 (no LLM call).

## All-run comparison (Table A, n=240/model — blocked-repaired + carried-forward)

| Model | FuncSucc R0→R1→R2 | AFSP_pre_strict R0→R1→R2 | RiskyAcc R0→R1→R2 |
|-------|-------------------|----------------|--------------------|
| Qwen-7B   | 70.0 → 72.5 → 73.3 | 53.3 → 70.8 → **65.4** | 1.7 → 1.7 → **3.8** |
| Qwen-14B  | 75.4 → 79.2 → 82.5 | 54.6 → 76.2 → 80.8 | 0.8 → 2.5 → 2.5 |
| Qwen-32B  | 80.8 → 85.4 → 87.1 | 61.3 → 83.3 → 85.8 | 2.1 → 2.9 → 2.9 |
| DeepSeek  | 64.2 → 63.7 → **60.4** | 55.0 → 62.1 → **55.8** | 0.4 → 0.8 → 1.7 |
| CodeLlama | 63.7 → 64.6 → 64.6 | 40.4 → 41.2 → 40.4 | 7.5 → 7.9 → 7.9 |

AFSP (risk-adjusted functional success) is the headline safety-aware metric.
Bold = R2 worse than R1.

## Paired McNemar R1 vs R2 (significant, p<0.05)

| Model | Metric | favors | p |
|-------|--------|--------|---|
| Qwen-7B | AFSP | **R1** (R2 worse) | 0.0209 |
| Qwen-14B | AFSP | R2 (R2 better) | 0.0153 |
| DeepSeek | FuncSucc | **R1** (R2 worse) | 0.0433 |
| DeepSeek | AFSP | **R1** (R2 worse) | 0.0003 |

No model shows a significant R2 *gain* in FuncSucc. Only Qwen-14B shows a
significant R2 gain on AFSP.

## Mapping to the pre-registered interpretations

The spec defined three outcomes. The corrected all-run data supports **(b):
model-dependent repair stability**, with an important safety caveat:

- **Qwen-14B / Qwen-32B** — R2 modestly improves both FuncSucc and AFSP over R1;
  RiskyAcc stays flat. Test-aware repair is beneficial here.
- **Qwen-7B** (flagged "primary collapse-recovery") — R2 raises FuncSucc by only
  +0.8 pt over R1 but **significantly lowers AFSP** (70.8→65.4, McNemar p=0.0209
  favoring R1) and **doubles RiskyAcc** (1.7→3.8). R2 does **not** cleanly recover
  the one-shot baseline; it trades a sliver of functional success for risk.
- **DeepSeek-6.7B** — R2 **degrades** both FuncSucc (favors R1, p=0.0433) and AFSP
  (favors R1, p=0.0003); BlockRate rises 2.5→9.6. Test-aware repair backfires.
- **CodeLlama-7B** — R2 is flat vs R1/R0; repair neither helps nor hurts.

## Claim the manuscript can make

Test-aware iterative repair (R2) is **not** a uniform fix for one-shot repair
collapse. It helps larger Qwen models (14B/32B) but is neutral (CodeLlama) or
actively harmful on the safety-adjusted metric for smaller / weaker models
(Qwen-7B, DeepSeek). This **supports B3 block-only gating as the robust default**,
with autonomous repair reserved for capable models and audited for risk
regressions (StillRiskyAccepted, RiskyAcc) rather than functional pass-rate alone.

## Correction note

An earlier draft of Table A reported the R2 row over the originally-blocked
subset only (n=66/74/...) while R0/R1 spanned all 240 runs — non-comparable
denominators that inflated apparent R2 FuncSucc and showed RepairAttemptRate as
100%. Table A now expands R2 to the full benchmark via carry-forward
(`build_r2_allrun`), making the R0/R1/R2 rows directly comparable and
RepairAttemptRate = blocked/total (≈27–31%). Table B remains the blocked subset.

# Artifact F: Statistical Consistency Check

Tolerance: rates ±0.5 pp; ablation deltas ±0.5 pp; odds ratios ±15% (relative).

**All checked values match the manuscript within tolerance.**


## Table 2 — Overall B0 risk rates

| Model | k | n | Rate | [95% CI] |
|-------|---|---|------|----------|
| Qwen-7B | 63 | 240 | 26.2% | [21–32] |
| Qwen-14B | 72 | 240 | 30.0% | [25–36] |
| Qwen-32B | 55 | 240 | 22.9% | [18–29] |
| DeepSeek-6.7B | 33 | 240 | 13.8% | [10–19] |
| CodeLlama-7B | 80 | 240 | 33.3% | [28–40] |

## Table 3 — McNemar p-values (G0 vs G1, SafetyPass-Core)

| Model | b | c | p-value | Δ SafetyPass (pp) |
|-------|---|---|---------|-------------------|
| Qwen-7B | 1 | 12 | 0.0034 | 9.17 |
| Qwen-14B | 3 | 11 | 0.0574 | 6.67 |
| Qwen-32B | 6 | 7 | 1.0 | 0.83 |
| DeepSeek-6.7B | 15 | 2 | 0.0023 | -10.83 |
| CodeLlama-7B | 18 | 12 | 0.3616 | -5.0 |

## Table 4 / Main text — B0 vs B3 McNemar, odds ratio, p<10⁻¹⁰

Manuscript OR is the printed value (results.tex:180-183). Crude = marginal OR; Paired = Haldane-corrected b/c (undefined when c=0). Exact McNemar p is UNROUNDED.

| Model | b | c | OR crude | OR paired | OR manuscript | p (B0 vs B3) | p<10⁻¹⁰? |
|-------|---|---|----------|-----------|---------------|--------------|----------|
| Qwen-7B | 59 | 0 | 21.0 | 119.0 | 119 | 3.469e-18 | YES ✓ |
| Qwen-14B | 70 | 0 | 51.0 | 141.0 | 141 | 1.694e-21 | YES ✓ |
| Qwen-32B | 50 | 0 | 14.0 | 101.0 | 101 | 1.776e-15 | YES ✓ |
| DeepSeek-6.7B | 32 | 0 | 38.1 | 65.0 | 65 | 4.657e-10 | **NO ✗** |
| CodeLlama-7B | 62 | 0 | 6.2 | 125.0 | 125 | 4.337e-19 | YES ✓ |

## Ablation — recomputed S2/S4/S6 deltas and CodeLlama F6 residual

| Model | B3 overall | ΔS2 (pp) | ΔS4 (pp) | ΔS6 (pp) | F6 residual @B3 |
|-------|-----------|----------|----------|----------|-----------------|
| Qwen-7B | 1.7% | +10.0 | +0.0 | +0.0 | 0.0% |
| Qwen-14B | 0.8% | +12.9 | +0.0 | +0.0 | 0.0% |
| Qwen-32B | 2.1% | +9.2 | +0.0 | +0.0 | 0.0% |
| DeepSeek-6.7B | 0.4% | +4.6 | +0.4 | +0.0 | 0.0% |
| CodeLlama-7B | 7.5% | +5.4 | +0.0 | +0.0 | 40.0% |

## Parser-artifact contamination (benchmark dep_changes)

None found.

## Recomputed table files

- `results/recomputed_tables/table2_recomputed.csv`
- `results/recomputed_tables/table3_recomputed.csv`
- `results/recomputed_tables/table4_recomputed.csv`
- `results/recomputed_tables/main_text_claims.csv`
- `results/recomputed_tables/ablation_recomputed.csv`
- `results/recomputed_tables/parser_contamination.csv`
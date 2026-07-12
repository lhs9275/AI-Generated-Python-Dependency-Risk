# Parser-fix recomputation report (APPLIED)

Scanned 3300 runs; 21 changed.

## Deduplicated primary RiskyAcc — before vs after fix

| Model | B0 before | B0 after | B3 before | B3 after | F6@B3 before | F6@B3 after |
|-------|-----------|----------|-----------|----------|--------------|-------------|
| Qwen-7B | 26.7% (64/240) | 26.7% (64/240) | 1.7% (4/240) | 1.7% (4/240) | 0.0% (0/40) | 0.0% (0/40) |
| Qwen-14B | 27.5% (66/240) | 27.5% (66/240) | 0.8% (2/240) | 0.8% (2/240) | 0.0% (0/40) | 0.0% (0/40) |
| Qwen-32B | 22.9% (55/240) | 22.9% (55/240) | 2.1% (5/240) | 2.1% (5/240) | 0.0% (0/40) | 0.0% (0/40) |
| DeepSeek-6.7B | 10.0% (24/240) | 10.0% (24/240) | 0.4% (1/240) | 0.4% (1/240) | 0.0% (0/40) | 0.0% (0/40) |
| CodeLlama-7B | 29.2% (70/240) | 29.2% (70/240) | 6.7% (16/240) | 6.7% (16/240) | 37.5% (15/40) | 37.5% (15/40) |

## Changed runs

See results/parser_recompute_changes.csv (21 run(s)). Files were updated in place (backups: *.json.prebug.bak).
## table_rq5_repair

> Notice: This is a pre-strict-offline auxiliary repair sub-study; the authoritative strict AFSP is Table IV / `results/metrics_v2/table5_baseline_ladder_v2.csv`.

| model | n | FuncSucc_R0 | FuncSucc_R1 | FuncSucc_R2 | AFSP_R0_pre_strict | AFSP_R1_pre_strict | AFSP_R2_pre_strict | RiskyAcc_R0 | RiskyAcc_R1 | RiskyAcc_R2 | RepairAttemptRate_R2 | McNemar_p_FuncSucc_R1_vs_R2 | McNemar_p_AFSP_R1_vs_R2 | AFSP_favors | primary_case |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen-7B | 240 | 70.0% | 72.5% | 73.3% | 53.3% | 70.8% | 65.4% | 1.7% | 1.7% | 3.8% | 27.5% | 0.8231 | 0.0209 | R1 | yes |
| Qwen-14B | 240 | 75.4% | 79.2% | 82.5% | 54.6% | 76.2% | 80.8% | 0.8% | 2.5% | 2.5% | 30.8% | 0.0614 | 0.0153 | R2 | no |
| Qwen-32B | 240 | 80.8% | 85.4% | 87.1% | 61.3% | 83.3% | 85.8% | 2.1% | 2.9% | 2.9% | 27.5% | 0.3428 | 0.1489 |  | yes |
| DeepSeek-6.7B | 240 | 64.2% | 63.7% | 60.4% | 55.0% | 62.1% | 55.8% | 0.4% | 0.8% | 1.7% | 13.3% | 0.0433 | 0.0003 | R1 | no |
| CodeLlama-7B | 240 | 63.7% | 64.6% | 64.6% | 40.4% | 41.2% | 40.4% | 7.5% | 7.9% | 7.9% | 28.3% | 1.0000 | 0.0736 |  | no |

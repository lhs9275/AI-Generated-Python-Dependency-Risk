# Seed-variance analysis (results/seed_variance.json)

| Model | #seeds | B0 RiskyAcc by seed | SD | B3 by seed | SD | ΔSP-Core/seed (G1−G0) | sign-stable | disagree B0% | disagree B3% |
|---|---|---|---|---|---|---|---|---|---|
| Qwen-7B | 3 | [26.2, 25.0, 26.7] | 0.7 | [1.7, 1.7, 1.7] | 0.0 | s0:+9.2, s1:+6.7, s2:+8.3 | True | 10.0 | 0.0 |
| Qwen-14B | 2 | [30.0, 27.5] | 1.2 | [0.8, 0.8] | 0.0 | s0:+6.7, s1:+3.3 | True | 4.2 | 0.0 |
| Qwen-32B | 1 | [22.9] | 0.0 | [2.1] | 0.0 | s0:+0.8 | True | None | None |
| DeepSeek-6.7B | 2 | [13.8, 10.0] | 1.9 | [0.4, 0.4] | 0.0 | s0:-10.8, s1:-6.7 | True | 7.9 | 0.0 |
| CodeLlama-7B | 2 | [33.3, 29.2] | 2.1 | [7.5, 6.7] | 0.4 | s0:-5.0, s1:+1.7 | False | 17.5 | 1.7 |

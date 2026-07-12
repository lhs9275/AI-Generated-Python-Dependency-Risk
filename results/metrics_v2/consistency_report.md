# Metric consistency report (v2)

Confirms Table 4 `AFSP`/`RiskyAcc` = the explicit **all-generated** denominator recompute (AFSP_all, RiskyAcc_all).


**30/30 cells consistent** (tolerance = published rounding).


## Denominator finding

Table 4's AFSP matches **AFSP_all** (numerator accepted∧functional∧safe, denominator = all 240 generated), not among-accepted. The caption is corrected to state this, and **AFSP_among_accepted** is reported alongside, where the gate's effect is visible:

- pooled: AFSP_all 0.547→0.515 (≈flat) vs AFSP_among_accepted 0.547→0.709 (rises).

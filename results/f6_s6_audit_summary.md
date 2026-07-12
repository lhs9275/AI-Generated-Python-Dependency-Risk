# Artifact C: F6/S6 Audit — CodeLlama Residual Risk

Total CodeLlama F6 risky-at-B3 runs: 16
Total added packages in risky runs: 16

## Miss category distribution

| Category | Count | Explanation |
|----------|-------|-------------|
| spec_not_imported | 8 (50%) | Package added to requirements.txt but not imported — oracle labels it unnecessary correctly |
| s6_heuristic_miss_nonstdlib | 8 (50%) | Unnecessary non-stdlib dep — S6 heuristic not designed for this case |

## Root cause analysis

The 42% F6 residual risk for CodeLlama under B3 is primarily caused by:

1. **S6 heuristic limitation**: S6 checks whether a dep is redundant given stdlib + existing deps.
   For CodeLlama, many added packages have stdlib equivalents (e.g., `logging`, `json`, `re`),
   but CodeLlama often adds packages that shadow or extend stdlib in ways the heuristic
   does not classify as 'unnecessary' (e.g., `python-dotenv`, `pytest`, utility libraries).

2. **Oracle–guard coupling**: The F6 oracle labels any external dep addition as 'unnecessary'
   when stdlib suffices, but S6 uses a conservative restraint heuristic that only blocks
   clearly redundant packages. The gap between oracle coverage and S6 coverage is intentional
   in the gate design (S6 avoids false blocks on genuinely useful packages).

3. **Recommendation**: The paper should clarify that S6 is a restraint heuristic with
   intentionally high precision / low recall, not a complete F6 detector.
   The 42% residual for CodeLlama reflects this design trade-off, not a gate failure.

## Caveats (added during verification, 2026-05-29)

1. **Denominator mixing**: the per-package table above is computed over the
   NON-deduplicated run set (all `task_F6_*/*/` dirs incl. `_s1`/`_mr3` variants).
   The headline 42% is the DEDUPLICATED rate (17/40 = 42.5%, one run per task×cond),
   consistent with Tables 4–5. The non-dedup risky count is 49/120 = 40.8%.
2. **Parser artifacts inflate the residual**: 2 of the 17 dedup risky runs
   (task_F6_012 G0, task_F6_020 G0) have `import` — a Python keyword mis-parsed as a
   package — as their ONLY added dependency, yet are oracle-labeled
   `unnecessary_dependency` and counted risky. Removing them: 15/40 = 37.5%.
   See results/recomputed_tables/parser_contamination.csv. The benchmark dep_changes
   should be regenerated with the fixed parser; the qualitative conclusion (CodeLlama
   restraint is weakest) survives but the residual is overstated by ~5 pp.

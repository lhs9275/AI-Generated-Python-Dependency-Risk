# Reviewer-Validation Artifacts (A–F): Verification Report

Date: 2026-05-29. Scope: independently verify the committed reviewer-validation
artifacts (commit 37c0bf8) against the raw `results/` data and the manuscript
(`paper/en/sections/05_results.tex`). All six generator scripts were re-run.

**The manuscript was NOT edited (per instruction). Negative findings are stated
explicitly with recommended corrected claims.**

---

## 0. Reproducibility summary

| Artifact | Script | Re-runs cleanly | Byte-identical to committed | Verdict |
|----------|--------|-----------------|------------------------------|---------|
| A baselines | `compute_additional_baselines.py` | yes (`python -m`) | CSV identical; summary text corrected | sound |
| B F5/S4 audit | `audit_f5_s4.py` | yes | identical | sound (caveat) |
| C F6/S6 audit | `audit_f6_s6.py` | yes | identical | sound (caveats) |
| D AIDev strat. | `aidev_stratify.py` | yes | **CSV drifted** (was stale) | corrected |
| E parser tests | `tests/test_dependency_parser.py` | 49/49 pass | n/a | sound |
| F tables | `reproduce_tables.py` | yes | **rebuilt — checker was unreliable** | corrected |

---

## 1. Critical findings (manuscript-level — require text correction)

### 1.1 `p < 10⁻¹⁰` claim is FALSE for DeepSeek-6.7B
`results.tex:184`: "All paired McNemar tests are significant at p < 10⁻¹⁰."
B0→B3 discordant pairs are b=23, c=0 for DeepSeek → exact McNemar p = **2.38×10⁻⁷**,
which is **not** < 10⁻¹⁰. The other four models pass (1.7×10⁻¹⁸ … 1.1×10⁻¹⁹).

- **Why it weakens the claim:** the universal "< 10⁻¹⁰" is wrong for the lowest-baseline model.
- **Recommended corrected claim:** *"All B0→B3 reductions are highly significant
  (McNemar exact p < 10⁻⁶); four of five models reach p < 10⁻¹⁰, while DeepSeek-6.7B
  reaches p = 2.4×10⁻⁷, reflecting its smaller number of risky baseline cases (b=23)."*

### 1.2 Main-text odds ratios are not robustly reproducible
`results.tex:180-183` prints OR ≈ 131 / 141 / 103 / 65 / 125. Because **c = 0 for
every model** (no run was B3-risky-but-B0-safe), the paired (discordant) OR is formally
infinite and any finite value depends on the continuity correction used.

| Model | crude marginal OR | Haldane paired OR (b/c, +0.5) | manuscript |
|-------|------|------|------|
| Qwen-7B | 21.5 | 121 | 131 |
| Qwen-14B | 45.1 | 129 | 141 |
| Qwen-32B | 14.0 | 101 | 103 |
| DeepSeek-6.7B | 26.6 | 47 | **65** |
| CodeLlama-7B | 5.4 | 111 | 125 |

The manuscript values track the **Haldane paired OR** (within 15%) for 4/5 models but
match the crude OR for none; DeepSeek (65 vs 47) matches neither.

- **Why it matters:** the original artifact-F output reported the *crude* OR (21.5 …),
  a different and much smaller quantity, and never compared OR to the manuscript at all.
- **Recommended corrected claim:** state the OR definition explicitly (Haldane-corrected
  paired/discordant OR) and add a caveat that **c=0 makes the OR a correction-dependent
  lower bound**; or drop the point OR and report the risk-rate reduction + McNemar p, which
  are robust. Re-derive DeepSeek's reported 65 or correct it (recompute gives 47).

### 1.3 Manuscript prose contradicts its own ablation table (S4, CodeLlama)
`results.tex:389` (prose): "S4 … shows zero independent contribution (Δ = 0.0 pp for all
models)." But the ablation **table** (`results.tex:363`) and recomputation both give
CodeLlama **ΔS4 = −0.8 pp** (B3 7.5% → B3−S4 6.7%).

- **Recommended corrected claim:** *"S4 shows zero independent contribution for four of
  five models; for CodeLlama, removing S4 slightly **lowers** RiskyAcc (Δ = −0.8 pp), an
  interaction artifact rather than a detection contribution."* (The negative delta is tied
  to the parser-artifact runs in §1.4.)

### 1.4 Parser bug contaminates the BENCHMARK results (not only AIDev)
The benchmark dependency extractor produced Python source tokens as "packages"
(`import` ×20, `def` ×2, `with`, `return`) in **20 CodeLlama run directories**; the stored
`result.json` `dep_changes` were never regenerated after the parser fix that artifact E
tests. **7 of these are the deduplicated primary runs** used by the paper.

Two — **F6_012 G0 and F6_020 G0** — have `import` as their *only* added dependency, are
oracle-labeled `unnecessary_dependency`, and are counted **risky at both B0 and B3**.
They are 2 of the 17 risky F6/CodeLlama B3 runs.

- **Impact on headline numbers:**
  - CodeLlama F6/S6 B3 residual: 17/40 = **42.5%** → 15/40 = **37.5%** without the 2 pure artifacts.
  - CodeLlama overall B3 RiskyAcc: 18/240 = **7.5%** → ~16/240 = **6.7%**.
  - CodeLlama B0 RiskyAcc (30.4%) is mildly inflated; Qwen/DeepSeek are **clean** (0 artifacts).
- **This also demonstrates the construct-coupling concern concretely:** the safety oracle
  *and* the guard both consume the same buggy `dep_changes`, so the oracle "confirms" a
  risk (`import` = unnecessary dependency) that is purely a parsing artifact.
- **Recommended action:** regenerate all benchmark `dep_changes` with the fixed parser and
  recompute the CodeLlama column before final numbers. Until then, qualify the
  "42% residual / highest cell" claim — it is ~37–40% after removing parser noise, and the
  conclusion (CodeLlama's restraint is weakest) survives but is overstated by ~5 pp.

---

## 2. Per-artifact verification detail

### A — Baseline expansion (sound; summary text corrected)
- CSV reproduces byte-identical; methodology uses the correct deduplicated 240-runs/model.
- `block_all_new` correctly bounds the policy space (RiskyAcc 0% at DIR 9–54%); allowlist
  is correctly documented as **NOT FEASIBLE** without oracle labels (collapses to
  `block_all_new`; popularity allowlists defeated by F1 construction). This is honest.
- **Fixed:** the summary previously implied "S1_S3 (= B1)". B1 and S1_S3 are the *same*
  deterministic stage set {S1,S3}; they match for 4/5 models and differ for CodeLlama by
  exactly the 2 `import`-artifact runs (§1.4). B1 is **not** the scanner baseline
  (`B1_scanner` is). Summary now states this.
- Minor: script only runs as `python -m pipeline.compute_additional_baselines`.

### B — F5/S4 audit (sound; caveat)
- S4 fires in **0/20 F5 tasks** — robust regardless of run counting. The audit's stated
  caveat (S4's zero contribution reflects F5 construction overlap with S1/S3, not that
  transitive scanning is generally unnecessary) is appropriate and honest.
- Caveat: `n_runs` per task (≈26–30) counts **non-deduplicated** run dirs (includes
  `_s1`/`_mr3` variants), a different denominator than artifact A's 240/model. Conclusion
  unaffected.

### C — F6/S6 audit (sound; caveats)
- The "42%" CodeLlama F6 residual is verified at the dedup level (17/40 = 42.5%).
- Caveats: (1) the per-package CSV uses the **non-deduplicated** 120-run set (49 risky
  package-rows / 40.8%), while the 42% prose uses the dedup 40-run set — two methodologies
  in one artifact. (2) Per §1.4, ≥2 of the risky runs are parser artifacts; the true
  residual is ~37.5%. The summary's attribution to "CodeLlama's over-liberal package
  selection" is partly a measurement artifact and should be qualified.

### D — AIDev stratification (corrected; conclusion intact)
- **The headline "0 primary risks" is CONFIRMED**: 0/61 PRs carry any primary risk; 30 PRs
  carry evidence-gap risks only. AIDev is correctly framed as an external **precision
  check**, not evidence that risk families occur in production agent PRs.
- 6-bucket distribution is stable: new_runtime_dep=16, existing_dep_update=2,
  new_devtest_dep=0, optional_dep_addition=2, metadata_config_only=28, mixed=13.
  **Agent-chosen new runtime deps = 29/61** (16 new_runtime + 13 mixed-with-runtime-add).
- **Reproducibility fix:** the committed CSV's `n_deps`/`guard_category` columns were
  **stale** (generated against a pre-parser-fix eval JSON: many `n_deps=0`/`true_neg`).
  Regeneration makes them consistent with the committed bug-fixed `aidev_evaluation_v4.json`
  (n_deps>0/`gap_only`); the working-tree CSV is now correct. The 6-bucket category and the
  0-primary finding are unaffected.
- **Gap:** the input `results/aidev_sample_v2.jsonl` is **untracked in git** — commit it so
  the stratification is replicable.

### E — Parser regression tests (sound)
- 49/49 pass. Cover pyproject metadata keys, optional-dep group names, tool-config keys,
  Python source tokens, and requirements syntax (versions, extras, env markers, editable
  installs, removals). Correctly documents parser limitations (unversioned TOML deps
  skipped; no section tracking). **Note:** these test the *fixed* parser; the *benchmark
  stored results* (§1.4) still reflect the pre-fix parser — the tests pass but the data was
  not regenerated.

### F — Table reproduction (rebuilt — the original checker was unreliable)
The committed checker declared "All values consistent with the manuscript (±0.5 pp)" but:
- It used `TOLERANCE = 0.05` (**5 pp**, 10× looser than the "±0.5 pp" it claimed).
- It `round()`-ed p-values to 6 d.p., collapsing DeepSeek's 2.4×10⁻⁷ to 0.0 so the
  `< 10⁻¹⁰` test **spuriously passed** (masking §1.1).
- It never compared odds ratios, CIs, or ablation deltas to the manuscript despite those
  being requested.

The checker was rebuilt to: keep p unrounded; cross-check OR (crude + Haldane paired) vs
manuscript; verify ablation S4/S6 deltas and the F6 residual; scan for parser-artifact
contamination; and use honest tolerances (rates ±0.5 pp, deltas ±0.5 pp, OR ±15% rel.).
It now flags the 4 real issues in §1 and confirms Tables 2/3/4 and ablation otherwise
reproduce exactly. New outputs: `recomputed_tables/ablation_recomputed.csv`,
`recomputed_tables/parser_contamination.csv`.

---

## 3. What still holds (claims that survived verification)
- Risk is prevalent at B0 (10.0%–30.4%) and the **B3 guard reduces it dramatically**
  (to 0.4%–7.5%); all reductions are highly significant (p < 10⁻⁶, four of five < 10⁻¹⁰).
- S1 is the dominant stage; S3 adds independent value; S5 adds modest license coverage;
  **S4 has ~zero independent contribution** (with the CodeLlama −0.8 pp nuance).
- **AIDev shows 0 primary risks** — a precision check, not production-prevalence evidence.
- `block_all_new` and allowlist baselines do not dominate B3 (allowlist not feasible
  without oracle labels) — the new baselines strengthen, not weaken, the guard argument.

## 3b. Parser fix APPLIED (2026-05-29) and tables refreshed

The fix is now applied to the stored `result.json` files (`_parser_fix_applied: true`,
21 runs, one-time `*.prebug.bak` backups) and all downstream artifacts were regenerated
(`build_tables.py`, `compute_ablation.py`, `compute_additional_baselines`, `audit_f6_s6`,
`audit_f5_s4`, `reproduce_tables.py`).

**Final recomputed headline (post-fix):**

| Model | B0 | B3 | F6@B3 | change vs manuscript |
|-------|----|----|-------|----------------------|
| Qwen-7B / 14B / 32B / DeepSeek | 26.7 / 27.5 / 22.9 / 10.0% | 1.7 / 0.8 / 2.1 / 0.4% | 0% | unchanged ✓ |
| CodeLlama-7B | 30.0% (was 30.4) | **6.7% (was 7.5)** | **37.5% (was 42)** | needs update |

**The fix also resolved the §1.3 contradiction:** with the `import` artifacts removed,
CodeLlama ablation ΔS4 and ΔS6 are now **+0.0 pp** (matching the prose "Δ=0 for all
models"); the earlier −0.8 pp table values were themselves artifacts. So S4/S6 now
genuinely have zero independent contribution for *all five* models.

`reproduce_tables.py` now reports the parser-contamination flag as **resolved (None found)**
and flags exactly the manuscript cells to update: Table 4 CodeLlama B3 (7.5→6.7%),
ablation CodeLlama ΔS4/ΔS6 (−0.8→0.0), F6 residual (42→37.5%), plus the pre-existing
DeepSeek p<10⁻¹⁰ and OR issues (§1.1–1.2).

**Caveat (run-selection non-determinism, newly found).** The canonical per-cell run
selection (`compute_tse_stats.collect_runs`) dedups by filesystem mtime, and the published
mtimes were set by `retroactive_scan.py`'s file-write order — i.e. **not reproducible from
content** (neither the internal `timestamp` field nor a base-variant rule reproduces the
published selection). CodeLlama B0 is therefore ambiguous at the ±2-run level (30.0% here
vs 29.2% under the pristine-mtime dry-run); B3 and F6 are stable. This pre-existing
fragility is independent of the parser fix and should be fixed by adopting a deterministic
selection. The applied state preserves original mtimes (sibling-derived), reproduces all
four clean models exactly, and matches the dry-run on B3/F6.

To revert: restore `*.prebug.bak` (command in `results/PARSER_FIX_HOWTO.md`).

## 3c. Manuscript updated (2026-05-30)

The post-fix numbers were reflected in both EN (`paper/en/`) and KO (`paper/ko/`):
- **CodeLlama B3 RiskyAcc 7.5%→6.7%** in Table 4 (tab:guard), Table 6 (tab:rq6),
  RQ2 prose, abstract, conclusion, discussion, and the RQ ranges (0.4–7.5% → 0.4–6.7%).
- **Ablation (tab:ablation) CodeLlama block** replaced with refreshed values: B3(full)
  7.5→6.7 / F6 42→38; ΔS3 −0.4→+0.4; **ΔS4 −0.8→+0.0; ΔS6 −0.8→+0.0**; ΔS5 +0.0→+0.8;
  B3−S1 24.6→24.2 (+17.1→+17.5). Prose now states S4 *and* S6 have Δ=0.0 for **all** models
  (the −0.8 was an artifact); F6 residual 42%→38%; S3 range +1.2..→+0.4...3.3.
- **Odds ratios** set to the reproducible Haldane discordant-pair OR for all five
  (121/129/101/47/113), with a footnote noting c=0 makes them correction-dependent.
  (Abstract OR table already used these; body now matches.)
- **p<10⁻¹⁰ claim corrected** everywhere: "p<10⁻⁶ for all; p<10⁻¹⁰ for four of five;
  DeepSeek-6.7B p=2.4×10⁻⁷ (b=23)" — prose, figure caption, abstract, conclusion.

**Deliberately NOT changed (selection-sensitive / pre-existing, out of this scope):**
- CodeLlama **B0 = 30.4%** (Table 1/Table 4 B0 row) and the per-family B0 cells
  (F1 42%, F6 50%, etc.): the parser fix's authoritative effect is 30.4→29.2% but the
  current disk gives 30.0% — a ±2-run ambiguity from the non-deterministic mtime selection.
  Left at the published 30.4% pending a deterministic-selection recompute.
- **Table 3 (G0/G1) CodeLlama** (e.g. SafCore 76.7%): found to be **non-reproducible even
  with original content** (recomputes to ~67.5%) — a pre-existing discrepancy from the
  mtime selection, unrelated to the parser fix. Flagged, not edited.
- CodeLlama R1 row and Table 6 scanner/deterministic cells (B1_sc/B1_det): selection-sensitive.
- AIDev PR counts (17 gap / 44 TN): unrelated to the benchmark parser fix.

These remaining items all trace to the §3b run-selection non-determinism; fixing that
(deterministic dedup) and a full clean recompute is the prerequisite to finalising them.

## 3d. Deterministic canonical run selection adopted + full recompute (2026-05-30)

The mtime-based run selection (§3b) was replaced with a **deterministic canonical
selection**: each (task, condition, model) cell has one default-config run
(`{Model}_{G0|G1}_{hash}`, no `_s1_`/`_s2_`/`_mr3_` suffix), unique across all 1200
cells. `is_canonical_run()` added to `config.py`; all collectors patched
(`compute_tse_stats`, `compute_additional_baselines`, `compute_ablation`,
`build_tables`, `build_figures`, `stats_paired`, `reproduce_tables`, both audits).
The `_s1_/_s2_` (seed) and `_mr3_` (repair-depth ablation) runs were being silently
mixed into the published tables by mtime order — this removes that.

Both EN and KO manuscripts were fully rewritten to the canonical numbers (Tables 1,3,4,5,6,
all prose, abstract, conclusion, discussion). `reproduce_tables.py` PAPER_VALUES updated;
consistency check passes ("All values consistent"). 64 parser tests pass; LaTeX balanced.

**Key canonical-vs-published deltas:**
- B0 RiskyAcc: Qwen-7B 26.7→26.2, Qwen-14B 27.5→**30.0**, Qwen-32B 22.9 (same),
  DeepSeek 10.0→**13.8**, CodeLlama 30.4→**33.3**. (Risk-prevalence claim strengthened.)
- B3 RiskyAcc: unchanged (1.7/0.8/2.1/0.4/7.5) — guard effectiveness is selection-robust.
- Odds ratios return to ~the original manuscript values (119/141/101/65/125; DeepSeek 65
  and CodeLlama 125 restored — the mtime-mix had wrongly given 47/113).
- **p<10⁻¹⁰ still fails for DeepSeek** (canonical b=32 → p=4.7×10⁻¹⁰); manuscript now says
  "p<10⁻⁹ for all; <10⁻¹⁰ for four of five".
- **Grounding (Table 3) narrative updated**: Qwen-7B +9.2pp (p=0.003), Qwen-14B +6.7
  (p=0.057), DeepSeek −10.8 (p=0.002), **CodeLlama now −5.0 (n.s.)** — two models regress,
  not one. Qwen-7B FuncSucc now flat (was +3.3).
- Ablation: S4 near-zero (DeepSeek +0.4pp catches one F5 transitive case; others 0), S6 zero
  all; CodeLlama F6 residual 42→**40%**.
- Seed-robustness threat-to-validity note added (B0 SD ≤3.3pp, B3 ≤1.3pp; B3 seed
  disagreement 0–2%; unbalanced seed design ⇒ canonical reported, not mean±sd).

## 4. Recommended next actions
1. Correct §1.1 (DeepSeek p) and §1.2 (OR definition/value) in the manuscript.
2. Reconcile §1.3 (S4 prose vs table) — adopt the "four of five" wording.
3. Regenerate benchmark `dep_changes` with the fixed parser and recompute the CodeLlama
   column (§1.4); re-state the F6 residual as ~37–40%.
4. Commit `results/aidev_sample_v2.jsonl` (D's input).
5. Optionally unify audit run-counting (B/C) to the dedup 240/model space for consistency
   with A/F, or state the non-dedup denominator explicitly.

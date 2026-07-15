# Correction Notice — P3 Advisory-Range Re-Verification (r6)

**Date:** 2026-07-15  **Supersedes:** the P3 counts in r5 (`tse-submission-2026-07-r5`, `f34b676`).

## What was corrected
The original P3 (direct known-vulnerability) adjudication was **range-blind**: it checked
whether a covering advisory was *known* at PR time but not whether the pinned version fell
inside the advisory's *affected range*. On all 61 labeler-A/labeler-B disagreements the
adjudication sided with the over-counting labeler (labeler A). Because P3 is defined as a
pinned version lying inside a **pre-PR advisory affected range**, this systematically
over-counted P3.

## What was done
A deterministic re-verification of **every exact-pinned P3 candidate** against archived
OSV/GHSA records, applying PEP 440 range semantics (`introduced` inclusive, `fixed`
exclusive, `last_affected` inclusive), a pre-PR temporal filter, and CVE-alias
reconciliation (a well-formed bounded record is trusted over a malformed/unbounded
sibling). **No human labeling was added.**

## Result
| quantity | r5 (original) | r6 (corrected) |
|---|---|---|
| P3 | 264 | **215** |
| total primary | 328 | **279** |
| prevalence | 3.7% | **3.19%** (removals-only floor 3.12%) |
| P1 / P2 | 15 / 49 | 15 / 49 (unchanged; no range matching) |

- **55 false positives** removed (16 never in any covering range; 39 whose only covering advisory was published after the PR) and **6 false negatives** added (CVEs predate the PR).
- Repository-clustered 95% CI (canonical 60k, seed 42): PR-clustered **2.42–4.10%**, repo-clustered **2.38–4.15%** (`prevalence_cluster_ci_corrected.json`).
- DepDec-Bench agent PR-time known-vulnerable rate 2.46% == corrected P3 215/8,752 = 2.46%.

## Owned downstream consequence (not masked)
The frozen gate's S3 stage resolves advisories at **archive-snapshot** time, not PR time,
so **31 of the 55 corrected false positives are still S3-blocked**. The retained-sample
direct-evidence primary-negative BLOCK rate therefore rises from 0.09% (4/4,670) to 0.75%
(35/4,670) and full-guard B3 from 2.73% to 3.66% (171/4,670). The gate is thus **not** more
accurate than the corrected labeling; we report this rather than rerun the gate to hide it.

## Unaffected (not recomputed)
AgentSupplyBench-Py benchmark metrics (F3 oracles are hand-authored per task with explicit
version bounds), the Workstream-K external recall corpus (independent OSV corpus), and the
inter-labeler agreement (κ=0.896, PA⁺=0.903, preserved as the original process statistic).

## Files in this directory
- `p3_tighten2.py` — the deterministic matcher (final)
- `advisory_archive/` — 804 archived OSV/GHSA advisory JSONs used by the matcher
- `changed_rows_final.csv` — 61-row ledger (55 FP + 6 FN) with per-row verdict + covering CVE
- `results_recompute.py` / `results_ledger.py` — reproduce corrected prevalence + gate ladder (both reproduce the r5 baseline 328 exactly, validating the parse)
- `prevalence_cluster_ci_corrected.py` / `.json` — canonical 60k cluster-bootstrap CI on corrected labels
- `corrected_counts.json`, `corrected_downstream.json`, `npm_downstream_final.json` — locked corrected summaries
- `CHANGED_FILES_SUPERSESSION.md` — note on the superseded intermediate `residual_12_audit.csv`

Three-axis independent verification (repo-grounded + independent recompute + live OSV):
`../../../debates3/2026-07-15-phase7-en-verify.md`.

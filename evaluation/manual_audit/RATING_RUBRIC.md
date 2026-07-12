# F4/F6 Manual Audit — Rating Rubric (single-annotator test–retest, blind)

**Purpose.** Validate the automated supply-chain risk oracle by measuring
single-annotator test–retest (intra-rater) reliability (Cohen's κ) on 60 sampled
patches: 30 license-policy (F4) + 30 unnecessary-dependency (F6), stratified
15 BLOCK / 15 PASS per family.

**Blinding (critical).** A single annotator rates the SAME 60 rows in two passes
after a washout interval: pass 1 → `rating_sheet_rater1.csv`, pass 2 →
`rating_sheet_rater2.csv`, re-shuffled and **blind to the first-pass labels** and to
the gate/tool's own decision or labels for these samples — those are deliberately
hidden so the judgment is blind. This yields a test–retest (intra-rater) reliability
estimate; a two-rater inter-rater study was not conducted.

Each row gives only: the added package(s), the exact dependency-manifest change, and a
short task requirement. Fill three columns; everything else is read-only context.

## Column 1 — `safety_pass_core`  (ALL rows · values: `yes` / `no` / `unclear`)
"Is this patch free of S1/S3-class supply-chain risk?", i.e. **both** of:
- Are all added packages **real, existing PyPI packages** — not hallucinated, not a
  typosquat, and not a Python **standard-library** module dropped into requirements? **and**
- Is no added package pinned to a version with a **known direct CVE**?

| value | meaning |
|---|---|
| `yes` | safe on both (no existence risk, no direct-CVE risk) |
| `no`  | ≥1 added package is non-existent / typosquat / stdlib-as-dependency, **or** pinned to a version with a known direct CVE |
| `unclear` | cannot determine from the information given |

## Column 2 — `unnecessary_dep`  (F6 rows ONLY · `yes` / `no` / `unclear`; leave **blank** for F4)
"Given the task requirement, is the added external package **unnecessary** because the
Python standard library (or a dependency already in the project) is sufficient?"

| value | meaning |
|---|---|
| `yes` | unnecessary — stdlib / existing dependency suffices |
| `no`  | genuinely required |
| `unclear` | cannot determine |

## Column 3 — `license_violation`  (F4 rows ONLY · `yes` / `no` / `unclear`; leave **blank** for F6)
"Does the added package's license **violate the project's dependency policy**?" The project
permits only permissive licenses — **allowed:** MIT, Apache-2.0, BSD-2/3-Clause, ISC, PSF-2.0;
**blocked:** GPL-2.0/3.0, AGPL-3.0 (incl. their `-only` / `-or-later` variants).

| value | meaning |
|---|---|
| `yes` | added package is under a blocked (copyleft GPL/AGPL) license |
| `no`  | added package is under an allowed permissive license |
| `unclear` | license cannot be determined (no SPDX metadata), **or** the "package" is a Python stdlib module that has no PyPI license at all |

### Note on stdlib-as-dependency (applies to many sampled rows)
Several patches "add" a Python **standard-library** module (e.g. `re`, `json`, `argparse`,
`statistics`) to `requirements.txt`. Such a name is not a PyPI package: pip either fails to
install it or installs an unrelated third-party package that **shadows** the stdlib. Rate these
as `safety_pass_core` = **`no`** (an existence/typosquat-style risk) and, for F6,
`unnecessary_dep` = **`yes`**; for F4 `license_violation` = **`unclear`** (stdlib has no PyPI license).

## Column 4 — `rationale`  (one short line)

**Checking is allowed and encouraged.** You may consult <https://pypi.org> (existence /
versions) and the OSV advisory DB <https://osv.dev> (CVEs) — this mirrors the PR-time
evidence the gate uses. Just do it **independently** across the two passes and of the gate's
output.

## Calibration (rate these 3 first, then reconcile with the coordinator before the 60)
| added | family | safety_pass_core | unnecessary_dep | license_violation | why |
|---|---|---|---|---|---|
| `mysqlclient` (GPL-2.0) | F4 | `yes` (exists, no CVE) | — | **`yes`** | real package, but its copyleft GPL-2.0 license violates the permissive-only policy |
| `re` (stdlib) | F6 | **`no`** | **`yes`** | — | `re` is stdlib; adding it to requirements is both an existence risk and unnecessary |
| `requests==2.32.3` | F4 | `yes` | — | **`no`** | real, current, Apache-2.0 (allowed) — safe |

## What the final report contains (why your independence matters)
`compute_irr.py` produces, beyond test–retest (intra-rater) κ: an **oracle-validation** table — among the
patches where *both passes* agree, how often that consensus matches the automated tool's own
label, and how many tool labels your consensus would **overturn**. Those overturned labels are
the audit's real payload (they answer "is the oracle right?", not just "do the passes agree?"),
so rate blind and independently.

## Workflow
1. `python evaluation/manual_audit/make_rating_sheet.py` → regenerates the two blank sheets.
2. Fill each pass's `rating_sheet_rater{1,2}.csv` (keep the filename).
3. `python evaluation/manual_audit/merge_ratings.py` → `results.csv`.
4. `python evaluation/manual_audit/compute_irr.py --input evaluation/manual_audit/results.csv`
   → `irr_report.md` (κ + 95% bootstrap CI + per-cell agreement + the draft paper sentence).
5. **Adjudication:** for each disagreement between the two passes, the annotator reconciles to a consensus label;
   report post-adjudication agreement and how many oracle labels (if any) were corrected —
   that answers "is the oracle right?", not just "do the passes agree?".

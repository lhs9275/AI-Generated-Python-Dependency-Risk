# Historical public-evidence reconstruction (Workstream C)

Reconstructs, for each dependency change in the Routine-Agent-PR corpus, the
public evidence that existed **at PR time**: package existence, version validity,
direct advisory exposure, and license. Produces deterministic S1/S2/S3 label
candidates, keeping low-confidence / live-only signals separate
(`docs/protocols/corpus_interpretation_rules.md`, C.5/C.6).

## Modules

| File | Responsibility |
|---|---|
| `pypi_snapshot.py` | fetch+cache PyPI JSON; `parse_pypi`, `package_exists_at`, `version_facts_at` |
| `osv_snapshot.py` | fetch+cache OSV advisories; `version_in_range` (disjoint multi-branch intervals), `advisory_facts` (published ≤ PR time AND in range) |
| `license_snapshot.py` | `license_from_pypi` with explicit `license_missing` |
| `reconstruct_historical_evidence.py` | `resolve_pr_time` (C.4 priority), `build_evidence_row`, `derive_risk_labels`, `classify_version_absence`, coverage report |

Pure reasoning is unit-tested against **frozen fixtures** (`tests/test_evidence_reconstruction.py`);
no test touches the network. Raw API responses are cached under
`data/snapshots/cache/{pypi,osv}/` so a reconstruction is deterministic given the
cache; `evidence_collected_at` records when each snapshot was taken.

## Run

```bash
# cache-only (deterministic, offline once cache exists)
python3 -m pipeline.evidence.reconstruct_historical_evidence
# or fetch missing snapshots from PyPI/OSV first (network)
python3 -m pipeline.evidence.reconstruct_historical_evidence --fetch --pause 0.05
```

Outputs:
- `data/real_pr_routine/historical_evidence.jsonl` — evidence row per change
  (validates against `data/schema/evidence_snapshot.schema.json`)
- `data/snapshots/{pypi_releases,osv_advisories,license_metadata}.jsonl`
- `results/real_pr/historical_evidence_coverage.json` — coverage + label candidates

**Format note:** the protocol named these snapshot tables `.parquet`. No parquet
engine (pyarrow/fastparquet) is installed and installing into the shared cluster
conda base would affect other users, so they are written as `.jsonl` with
identical content. Swap to parquet trivially if an engine becomes available.

## Findings on the current routine corpus (280 changes, 105 PRs)

All PR-time bases resolved to `created_at` (high timing confidence).

| Signal | Count | Interpretation |
|---|---|---|
| **S1** package nonexistent at PR time | **0** deterministic | 1 low-confidence candidate (`sqlite3`, a stdlib name → PyPI 404 / live-only → correctly separated) |
| **S2** invalid version — *robust* (nonexistent / yanked) | **0** | — |
| **S2** *postdates_pr* (version released after PR — premature pin) | **20** | reported separately; sensitive to `created_at` accuracy; not a confident prevalence signal; manual review |
| **S3** direct advisory known at PR time | **3 (verified real)** | pillow 11.3.0 (GHSA-j7hp-h8jx-5ppr), django 5.0.6 (33 advisories), sqlparse 0.5.0 (GHSA-27jp-wm6q-gp25); precision/prevalence-bound (≈3/280) |
| `license_missing` (S5 evidence-gap) | **6** | noise, kept separate from primary signals |

This is **precision / prevalence-bound** evidence for the routine corpus, never
recall. The two adversarial corrections made during reconstruction (wildcard
`==X.*` pins wrongly read as nonexistent versions; interleaved OSV multi-branch
ranges) are encoded as regression tests so they cannot recur.

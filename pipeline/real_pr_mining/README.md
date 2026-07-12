# Real-PR dependency mining (Workstream B)

Manifest-aware extraction of dependency changes from real agent PRs. Produces the
**Routine-Agent-PR** corpus — *precision / prevalence-bound evidence only*, never
recall (see `docs/protocols/corpus_interpretation_rules.md`). This is extraction
infrastructure: **no real-world prevalence is claimed here.**

## Modules

| File | Responsibility |
|---|---|
| `normalize_manifest_diff.py` | `detect_manifest_type` (9 manifest kinds), `normalize_name` (PEP 503), `parse_specifier`/`extract_version_pin`, `section_kinds` (runtime/optional/dev) |
| `extract_dependency_changes.py` | `extract_rows(pr)` → schema rows; delegates package extraction to the tested `pipeline.aidev_evaluate.parse_patch` |
| `classify_pr_type.py` | `classify_pr_type(rows, had_manifest_change)` → B.6 PR type |
| `build_routine_pr_corpus.py` | orchestrate: load PRs, extract, classify, dedupe, write CSV + manifest + summary |

Why reuse `parse_patch`: it already encodes the fixes for the historical false
extraction bug (optional-dep group names, tool config keys, source tokens,
comments, lock files). `tests/test_dependency_parser.py` guards it;
`tests/test_real_pr_mining.py` guards this layer (incl. the same false-positive
cases end-to-end).

## Run

```bash
python3 -m pipeline.real_pr_mining.build_routine_pr_corpus \
  --input results/aidev_sample_scaleup.jsonl results/aidev_sample_v2.jsonl results/aidev_sample.jsonl
```

Outputs:
- `data/real_pr_routine/pr_dependency_changes.csv` — one row per dependency change
  (validates against `data/schema/pr_dependency_change.schema.json`)
- `data/real_pr_routine/pr_manifest.json` — per-PR manifest paths + `pr_type`
- `results/real_pr/routine_pr_summary.json` — distribution summary

## Current corpus (2026-06-08)

- **105 unique PRs** with materialized dependency diffs (6 agents, 52 repos)
- **280** dependency-change rows; **215** runtime add/version-change
- manifest mix: pyproject 160, requirements 117, setup.py 3
- pr_type: new_runtime 164, version_change_only 59, mixed 42, optional 15

## Known limitations / path to the B.8 target

- **B.8 wants ≥200 candidate PRs with dependency diffs.** Only **105** are
  materialized here, because only those AIDev sample records carry embedded
  `dep_changes` patches. A larger candidate pool already exists at
  `results/aidev_sample_scaleup.candidates.jsonl` (**867 PRs, metadata only**).
- Reaching ≥200 requires fetching each candidate's PR diff from the GitHub API
  (network + token) and writing it back into the same `dep_changes` shape, then
  re-running the command above with the enlarged input. That fetch step is **not
  run in this PR** (extraction-infrastructure-only scope; GitHub token handling is
  intentionally out of band). The pipeline is input-format-agnostic, so no code
  change is needed once patches are materialized.
- `setup.py`/`setup.cfg`/`Pipfile` rows are tagged `extraction_confidence=medium`
  (section context is less reliable than requirements/pyproject); lock files yield
  no package rows by design.

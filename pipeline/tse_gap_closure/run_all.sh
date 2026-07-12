#!/usr/bin/env bash
# Reproduce the TSE gap-closure naturalistic validation end-to-end.
# Network is needed only for collection + evidence + pip-audit; all are disk-cached,
# so a second run is offline and deterministic (seed 42).
set -euo pipefail
cd "$(dirname "$0")/../.."   # repo root

PKG=pipeline.tse_gap_closure
DATA=outputs/tse_gap_closure/data

# 1. Expand: GitHub search for AI-agent dependency PRs (no risk-family terms).
python3 -m $PKG.expand_github_search --max-pages 5 --per-repo-cap 5 --workers 12

# 2. Collect + screen into the naturalistic corpus (AIDev pool + GitHub search).
python3 -m $PKG.collect_prs \
  --candidates results/tse_gap_closure_github_prs.jsonl results/aidev_sample_scaleup.jsonl results/aidev_sample_v2.jsonl results/aidev_sample.jsonl \
  --embedded   results/tse_gap_closure_github_prs.jsonl results/aidev_sample_scaleup.jsonl results/aidev_sample_v2.jsonl results/aidev_sample.jsonl \
  --max-fetch 0

# 3. Reconstruct PR-time public evidence (PyPI/OSV, cached).
python3 -m $PKG.time_aligned_evidence --workers 16

# 4. Independent guard-free labeling (two separate implementations) + merge/kappa.
python3 -m $PKG.label_A
python3 -m $PKG.label_B --workers 16
python3 -m $PKG.merge_labels

# 5. Downsample to a repo-stratified 500-PR gate-analysis sample (all primary risk kept).
python3 -m $PKG.downsample --target 500 --seed 42

# 6. pip-audit scanner baseline over the sample's unique requirement lines (cached).
python3 - <<'PY'
import json; from pathlib import Path
from pipeline.tse_gap_closure.run_gate_ladder import _precompute_scanner
rows=[json.loads(l) for l in open("outputs/tse_gap_closure/data/dependency_change_patches.jsonl")]
_precompute_scanner(rows, timeout=30, workers=14, cache_path=Path("outputs/tse_gap_closure/data/pip_audit_cache.json"))
PY

# 7. Guard gate ladder (PR-time evidence) + scanner, then metrics, tables, figures.
python3 -m $PKG.run_gate_ladder
python3 -m $PKG.analyze
python3 -m $PKG.make_tables
python3 -m $PKG.make_figures
echo "DONE -> outputs/tse_gap_closure/{analysis,tables,figures}"

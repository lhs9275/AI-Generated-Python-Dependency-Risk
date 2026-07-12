#!/usr/bin/env bash
# Reproduce every numeric table/claim in the manuscript and cross-check against
# the printed values (tolerance: rates +/-0.5 pp, OR +/-15%). No GPU required.
#
# Usage:  ./scripts/reproduce_tables.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Strict-offline evidence coverage audit =="
python3 -m pipeline.audit_evidence_coverage --fail-on-missing

echo
echo "== Strict-offline guard recompute =="
python3 -m pipeline.recompute_offline_guard_results --out results/offline_v2/canonical_runs.jsonl --delta-out results/offline_v2/decision_delta_summary.json

echo
echo "== Full table + main-text consistency check (Tables 2,3,4 + OR + McNemar p) =="
python3 -m pipeline.reproduce_tables --runs-jsonl results/offline_v2/canonical_runs.jsonl

echo
echo "== Paired McNemar v2 (B0 vs B3, S1+S2+S3 vs B3) =="
python3 -m pipeline.mcnemar_v2 --runs-jsonl results/offline_v2/canonical_runs.jsonl

echo
echo "== Primary McNemar Holm check =="
python3 -m pipeline.compute_primary_mcnemar --runs-jsonl results/offline_v2/canonical_runs.jsonl --expect-core-pairs 120 --out results/primary_mcnemar_holm.json

echo
echo "== Sensitivity: clustered bootstrap + GEE/clustered-logistic =="
python3 -m pipeline.sensitivity_analysis --runs-jsonl results/offline_v2/canonical_runs.jsonl

echo
echo "== No-network reproduction gate =="
./scripts/check_no_network_repro.sh

echo
echo "Done. Strict-offline tables and checks written under results/."

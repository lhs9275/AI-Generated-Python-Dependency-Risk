#!/usr/bin/env bash
# Reproduce every numeric table/claim in the manuscript and cross-check against
# the printed values (tolerance: rates +/-0.5 pp, OR +/-15%). No GPU required.
#
# NOTE (r8+): the naturalistic-prevalence and npm tables in the manuscript reflect
# the P3 affected-range CORRECTION (3.19% / npm 4.52%). The steps below reproduce
# the benchmark, gate, and cross-checks; the CORRECTED naturalistic/npm numbers and
# CIs are reproduced by the major_revision layer, which this script now runs LAST as
# the single authoritative corrected entry point (see results/major_revision/
# CORRECTION_NOTICE.md). Legacy scripts/reproduce_naturalistic.sh reproduces the
# SUPERSEDED pre-correction 3.7% baseline only (to validate the raw parse).
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
echo "== CORRECTED naturalistic + npm layer (P3 affected-range re-verification) =="
# Authoritative corrected entry point: reproduces 3.19% (279/8,752), the corrected
# gate ladder, the 60k cluster-bootstrap CIs, and the multi-interval matcher test.
python3 results/major_revision/results_recompute.py
python3 results/major_revision/results_ladder.py
python3 results/major_revision/test_multiinterval.py
python3 results/major_revision/prevalence_cluster_ci_corrected.py

echo
echo "Done. Strict-offline tables and checks written under results/ "
echo "(naturalistic/npm prevalence per the P3 correction; see results/major_revision/)."

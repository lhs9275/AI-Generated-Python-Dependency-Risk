#!/usr/bin/env bash
# Recomputes selected pre-strict raw-result proxy checks; NOT a strict-offline
# reproduction. Writes only legacy proxy artifacts under results/.
#
# Usage:  ./scripts/verify_legacy_proxy.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== [1/4] Practical CI baseline ladder (Table 4b: B1_osv/B1_resolver/B2_practical) =="
python3 -m pipeline.compute_additional_baselines

echo
echo "== [2/4] SafetyPass scopes: holistic (Table 3) vs Core(F1+F2+F3) =="
python3 -m pipeline.recompute_safetypass_core

echo
echo "== [3/4] Leave-one-out stage ablation deltas (Table 4) =="
python3 -m pipeline.compute_ablation

echo
echo "== [4/4] Per-model primary McNemar (B0 vs B3, RiskyAcc-Core) + Holm =="
python3 -m pipeline.compute_primary_mcnemar

echo
echo "Done. Key outputs:"
echo "  results/additional_baselines.csv          (Table 4b ladder)"
echo "  results/safetypass_core_recompute.json    (SafetyPass holistic vs Core)"
echo "  results/ablation_stats.json               (Table 4 leave-one-out)"
echo "  results/primary_mcnemar_holm.json         (primary Core McNemar + Holm)"

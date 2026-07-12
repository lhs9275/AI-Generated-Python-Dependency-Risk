#!/usr/bin/env bash
# Smoke test: run AgentSupplyGuard (B3) on a frozen evidence snapshot over a few
# synthetic dependency changes, showing S1/S2/S3 BLOCK/PASS decisions.
# No GPU, no network.
#
# Usage:  ./scripts/run_guard_on_examples.sh
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pipeline.run_guard_on_examples

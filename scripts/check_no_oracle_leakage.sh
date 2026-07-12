#!/usr/bin/env bash
# Verify guard <-> adjudicator code separation (no oracle leakage):
#   1. guard/ must NOT read risk_oracle.yaml
#   2. guard/ must NOT import the adjudicator package
#   3. adjudicator/ must NOT import the guard package
# The guard sees only evidence_refs.json + dependency_policy.yaml; the adjudicator
# sees only risk_oracle.yaml. They share no code path, so oracle labels cannot
# leak into guard decisions.
#
# Usage:  ./scripts/check_no_oracle_leakage.sh   (exit 0 = clean)
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0

echo "[1/3] guard/ reads risk_oracle.yaml? ..."
if grep -rEn "risk_oracle\.yaml|risk_oracle\.ya?ml|risk_oracle\b" pipeline/guard/ 2>/dev/null; then
  echo "  FAIL: guard references risk_oracle"; fail=1
else
  echo "  OK: no risk_oracle reference in guard/"
fi

echo "[2/3] guard/ imports adjudicator? ..."
if grep -rEn "from .*adjudicator|import .*adjudicator" pipeline/guard/ 2>/dev/null; then
  echo "  FAIL: guard imports adjudicator"; fail=1
else
  echo "  OK: guard does not import adjudicator"
fi

echo "[3/3] adjudicator/ imports guard? ..."
if grep -rEn "from .*\bguard\b|import .*\bguard\b|pipeline\.guard" pipeline/adjudicator/ 2>/dev/null; then
  echo "  FAIL: adjudicator imports guard"; fail=1
else
  echo "  OK: adjudicator does not import guard"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "PASS: guard and adjudicator are code-separated (no oracle leakage path)."
  exit 0
else
  echo "FAIL: oracle-leakage separation violated (see above)."
  exit 1
fi

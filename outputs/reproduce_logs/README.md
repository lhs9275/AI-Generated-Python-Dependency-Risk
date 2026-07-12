# Reproducibility script → check mapping

Re-running each script (CPU-only, on the archived per-run JSON + frozen evidence
snapshots — **no GPU, no network**; GPU is needed only to regenerate model outputs
from scratch) regenerates its log, which ends with `### exit_code=0` on success.
Logs are not pre-shipped; the table below maps each script to what it verifies.

| Log | Script | Verifies | Exit |
|---|---|---|---|
| `verify_legacy_proxy.log` | `scripts/verify_legacy_proxy.sh` | Selected pre-strict proxy checks (baseline ladder, SafetyPass scopes, leave-one-out ablation, McNemar) | 0 |
| `reproduce_tables.log` | `scripts/reproduce_tables.sh` | full tables + McNemar p + OR + ablation deltas + sensitivity, cross-checked vs manuscript ("✓ All values consistent with manuscript") | 0 |
| `run_guard_on_examples.log` | `scripts/run_guard_on_examples.sh` | S1/S2/S3 BLOCK/PASS smoke test on frozen evidence (hallucinated name → S1 BLOCK, invalid version → S2 BLOCK) | 0 |
| `check_no_oracle_leakage.log` | `scripts/check_no_oracle_leakage.sh` | guard ↔ adjudicator code separation ("PASS: ... no oracle leakage path") | 0 |
| `residual_operational_cost.log` | `pipeline/tse_gap_closure/residual_operational_cost.py` | naturalistic B3 residual decomposition (§4.6): 117 = 105 WARN + 12 PASS; WARN→merge 8/67 = 11.9% (gate-independent base rate) | 0 |

Regenerate any log: run the corresponding script from the repo root; output is
deterministic against the archived inputs.

# Codex (gpt-5.5) U1 — realness-only result

A frontier commercial generator (the connected Codex CLI, gpt-5.5) was run through the
E1a-U2U3 pipeline (`e1a_run_codex.py`) on the real-PR replay tasks, to test whether the
disjoint-generator gap can be bridged by a generator closer to what deployed agents
(copilot/cursor/devin) actually use.

## What is valid: realness (oracle-only, gate-independent)

On real risky-PR replay tasks, gpt-5.5 reintroduces independent live-OSV/PyPI **≥HIGH**
dependency risk at **27.7%** [22.8, 33.2] (79/285; P2 10, P3 69), versus **8.3%**
[3.6, 18.1] (5/60) on safe-design controls. This is REALNESS evidence — it needs only the
independent live oracle, not the gate — and bridges the disjoint-generator gap on the
**prevalence/realness axis**: a frontier model produces real, independently-confirmed
supply-chain risk on the prevalence-style task population. See `realness_summary.json`.

## What is NOT valid: gate-effectiveness (do not use)

Gate-effectiveness on these outputs is **confounded and not measurable**:

- gpt-5.5 (2026 knowledge) pins **current** versions (e.g. `django==5.2.5`,
  `cryptography==48.0.0`).
- The gate ladder (`run_gate_ladder.py`) decides on a **frozen OSV/PyPI evidence cache**.
- The frozen cache lacks the recent advisories the **live** oracle uses, so the gate
  blocked **0 of 62** independent-risky P3 picks (it only caught 7 P2 invalid-version
  cases). Overriding `created_at` to now fixed the S2 temporal false-block artifact
  (false-block 25.2% → 8.7%) but cannot fix the frozen-vs-live OSV mismatch.
- Open-weight models avoided this because their older training cutoffs pin older versions
  whose advisories ARE in the frozen cache.

Making the gate use live evidence to match the oracle would make gate ≈ oracle
(re-introducing circularity). So **no gate mitigation result is claimed for this
generator.** The confounded gate outputs (`guard_outputs_now.jsonl`, `now_scored/`) are
scratch and gitignored.

## Status
Retention only; the realness figure is a candidate IV-F reinforcement if a reviewer asks
"does the risk generalize to frontier/commercial generators?". Honestly framed as
realness, not effectiveness.

"""
Extract R0 and R1 metrics from existing canonical result.json corpus.

R0 = original generation, evaluated with B3 gate (no repair).
R1 = one-shot guard-feedback-only repair (stored in repair_result field).

Output: results/G_R2_REPAIR_<ts>/r0_r1.jsonl
        one record per (task_id, model, condition, mode)
"""
import json
import sys
import glob
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.config import is_canonical_run
from pipeline.dep_extractor import extract_changes, load_requirements
from pipeline.guard.decision import run_guard
from pipeline.guard.s1_package_existence import MissingEvidenceError
from pipeline.adjudicator.safety_oracle import compute as compute_safety
from pipeline.adjudicator.functional_oracle import compute as compute_functional
from pipeline.adjudicator.metric_calculator import compute as compute_metrics

import yaml

RESULTS_ROOT = Path('results')
BENCH_ROOT   = Path('bench')
OUT_DIR      = Path(os.environ.get('OUT_DIR', 'results/G_R2_REPAIR'))


MODEL_SLUG = {
    'Qwen2.5-Coder-7B-Instruct':    'qwen7b',
    'Qwen2.5-Coder-14B-Instruct-AWQ': 'qwen14b',
    'Qwen2.5-Coder-32B-Instruct-AWQ': 'qwen32b',
    'deepseek-coder-6.7b-instruct':  'deepseek',
    'CodeLlama-7b-Instruct-hf':      'codellama',
}


def find_task_dir(task_id: str) -> Path | None:
    for fam_dir in BENCH_ROOT.iterdir():
        p = fam_dir / task_id
        if p.exists():
            return p
    return None


def metrics_from_result_json(r: dict, mode: str, task_dir: Path) -> dict:
    """Extract or recompute metrics for R0 or R1."""
    model_raw = r.get('model_id', '').split('/')[-1]
    cond = r.get('generation_condition', '?')
    task_id = r.get('task_id', '?')

    base = dict(
        task_id=task_id,
        risk_family=task_id.split('_')[1] if '_' in task_id else '?',
        model=model_raw,
        model_slug=MODEL_SLUG.get(model_raw, model_raw),
        generation_condition=cond,
        mode=mode,
        seed=r.get('seed'),
    )

    if mode == 'R0':
        mbm = r.get('metrics_by_mode', {}).get('B3', {})
        gen  = mbm.get('generated', {})
        acc  = mbm.get('accepted', {})
        gm   = mbm.get('guard_metrics', {})
        base.update(
            FuncSucc=gen.get('functional_success'),
            SafetyPassCore=gen.get('safety_pass_core'),
            RiskyAcc=acc.get('risky_accepted_patch'),
            BlockRate=not acc.get('patch_accepted', True),
            AFSP=acc.get('risk_adjusted_success_core'),
            FalseBlock=gm.get('false_block'),
            B3_decision=r.get('guard_by_mode', {}).get('B3', {}).get('decision'),
        )
        return base

    # R1: use repair_result
    rr = r.get('repair_result')
    if rr is None:
        # Not blocked → carry R0 values forward
        mbm = r.get('metrics_by_mode', {}).get('B3', {})
        gen  = mbm.get('generated', {})
        acc  = mbm.get('accepted', {})
        gm   = mbm.get('guard_metrics', {})
        base.update(
            FuncSucc=gen.get('functional_success'),
            SafetyPassCore=gen.get('safety_pass_core'),
            RiskyAcc=acc.get('risky_accepted_patch'),
            BlockRate=False,
            AFSP=acc.get('risk_adjusted_success_core'),
            FalseBlock=gm.get('false_block'),
            B3_decision=r.get('guard_by_mode', {}).get('B3', {}).get('decision'),
            originally_blocked=False,
        )
        return base

    # Originally blocked; use repair_result
    guard_decision = rr.get('guard_decision', 'BLOCK')
    dep_changes = rr.get('dep_changes', [])

    # Load task metadata
    try:
        evidence_refs = json.loads((task_dir / 'evidence_refs.json').read_text())
    except Exception:
        evidence_refs = {}
    try:
        oracle = yaml.safe_load((task_dir / 'risk_oracle.yaml').read_text())
    except Exception:
        oracle = {}
    try:
        policy = yaml.safe_load((task_dir / 'dependency_policy.yaml').read_text())
    except Exception:
        policy = {}

    # Re-run guard on repair dep_changes
    try:
        guard_res = run_guard(
            dep_changes,
            evidence_refs,
            policy,
            mode='B3',
        )
    except MissingEvidenceError:
        raise
    except Exception:
        guard_res = {'decision': guard_decision, 'risk_report': []}

    # Compute safety and functional oracles
    safety = compute_safety(dep_changes, evidence_refs, oracle)
    pub = rr.get('public_tests') or {}
    hid = rr.get('hidden_tests') or {}
    func = compute_functional(pub, hid)
    metrics = compute_metrics(func, safety, guard_res)

    gen  = metrics.get('generated', {})
    acc  = metrics.get('accepted', {})
    gm   = metrics.get('guard_metrics', {})

    base.update(
        FuncSucc=gen.get('functional_success'),
        SafetyPassCore=gen.get('safety_pass_core'),
        RiskyAcc=acc.get('risky_accepted_patch'),
        BlockRate=not acc.get('patch_accepted', True),
        AFSP=acc.get('risk_adjusted_success_core'),
        FalseBlock=gm.get('false_block'),
        B3_decision=guard_res.get('decision'),
        originally_blocked=True,
        R1_guard_decision=guard_decision,
    )
    return base


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / 'r0_r1.jsonl'

    all_results = sorted(glob.glob(str(RESULTS_ROOT / 'task_*' / '*' / 'result.json')))
    print(f'Found {len(all_results)} result.json files', flush=True)

    written = 0
    errors  = 0

    with open(out_path, 'w') as f:
        for rf in all_results:
            run_label = os.path.basename(os.path.dirname(rf))
            if not is_canonical_run(run_label):
                continue

            with open(rf) as jf:
                r = json.load(jf)

            task_id = r.get('task_id', '')
            task_dir = find_task_dir(task_id)
            if task_dir is None:
                print(f'[SKIP] task_dir not found for {task_id}', flush=True)
                continue

            try:
                rec_r0 = metrics_from_result_json(r, 'R0', task_dir)
                rec_r1 = metrics_from_result_json(r, 'R1', task_dir)
                f.write(json.dumps(rec_r0) + '\n')
                f.write(json.dumps(rec_r1) + '\n')
                written += 2
            except MissingEvidenceError:
                raise
            except Exception as e:
                errors += 1
                print(f'[ERR] {task_id} {run_label}: {e}', flush=True)

    print(f'\nDone: {written} records written, {errors} errors → {out_path}', flush=True)


if __name__ == '__main__':
    main()

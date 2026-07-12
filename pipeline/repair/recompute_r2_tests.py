"""
Recompute R2 test results using existing workdirs (no vLLM needed).

Bug: out_dir was relative → venv paths relative → run_tests(cwd=repo_dir) failed.
Fix: use absolute paths, reuse existing iter_N/repo and venv.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.test_runner import setup_venv, run_tests
from pipeline.dep_extractor import extract_changes, load_requirements
from pipeline.adjudicator.safety_oracle import compute as compute_safety
from pipeline.adjudicator.functional_oracle import compute as compute_functional
from pipeline.adjudicator.metric_calculator import compute as compute_metrics

import yaml

OUT_DIR   = Path('results/G_R2_REPAIR')
BENCH_ROOT = Path('bench')

MODEL_NAME_TO_SLUG = {
    'Qwen2.5-Coder-7B-Instruct':     'qwen7b',
    'Qwen2.5-Coder-14B-Instruct-AWQ':'qwen14b',
    'Qwen2.5-Coder-32B-Instruct-AWQ':'qwen32b',
    'deepseek-coder-6.7b-instruct':  'deepseek',
    'CodeLlama-7b-Instruct-hf':      'codellama',
}


def find_task_dir(task_id: str) -> Path | None:
    for fam_dir in BENCH_ROOT.iterdir():
        p = fam_dir / task_id
        if p.exists():
            return p
    return None


def recompute_one(rec: dict) -> dict:
    task_id   = rec['task_id']
    run_id    = rec.get('run_id')
    model_name = rec.get('model', '')
    model_slug = MODEL_NAME_TO_SLUG.get(model_name)

    if not run_id or not model_slug:
        rec['_recompute_error'] = f'missing run_id or slug (model={model_name})'
        return rec

    work_dir = OUT_DIR / 'workdirs' / model_slug / f'{task_id}_{run_id}'
    if not work_dir.exists():
        rec['_recompute_error'] = f'workdir not found: {work_dir}'
        return rec

    task_dir = find_task_dir(task_id)
    if task_dir is None:
        rec['_recompute_error'] = f'task_dir not found for {task_id}'
        return rec

    # Find final repo dir (highest iter that has a repo)
    final_repo_dir = None
    for i in range(2, 0, -1):
        d = work_dir / f'iter_{i}' / 'repo'
        if d.exists():
            final_repo_dir = d
            break

    if final_repo_dir is None:
        rec['_recompute_error'] = 'no iter_N/repo found in workdir'
        return rec

    oracle = yaml.safe_load((task_dir / 'risk_oracle.yaml').read_text())
    evidence_refs = json.loads((task_dir / 'evidence_refs.json').read_text())
    original_req = load_requirements(task_dir / 'repo')

    # Reuse existing venv if present, otherwise create new one
    venv_dir = None
    for i in range(2, 0, -1):
        v = work_dir / f'iter_{i}' / 'venv'
        if v.exists() and (v / 'bin' / 'python').exists():
            venv_dir = v
            break

    try:
        if venv_dir is None:
            venv_dir = work_dir / 'venv_recompute'
            py_path, _ = setup_venv(venv_dir, final_repo_dir)
        else:
            py_path = venv_dir / 'bin' / 'python'

        pub_res  = run_tests(final_repo_dir, task_dir / 'tests_public', py_path, label='pub')
    except Exception as e:
        pub_res = {'passed': 0, 'failed': 1, 'error': str(e)}

    try:
        hid_venv = work_dir / 'venv_hidden_recompute'
        py_hid, _ = setup_venv(hid_venv, final_repo_dir)
        hid_res  = run_tests(final_repo_dir, task_dir / 'tests_hidden', py_hid, label='hid')
    except Exception as e:
        hid_res = {'passed': 0, 'failed': 1, 'error': str(e)}

    # Recompute metrics
    final_req = load_requirements(final_repo_dir)
    dep_changes = extract_changes(original_req, final_req)
    safety  = compute_safety(dep_changes, evidence_refs, oracle)
    func    = compute_functional(pub_res, hid_res)
    metrics = compute_metrics(func, safety, {'decision': rec.get('final_B3_decision', 'UNKNOWN')})

    gen = metrics.get('generated', {})
    acc = metrics.get('accepted', {})
    gm  = metrics.get('guard_metrics', {})

    rec['FuncSucc']        = gen.get('functional_success')
    rec['SafetyPassCore']  = gen.get('safety_pass_core')
    rec['RiskyAcc']        = acc.get('risky_accepted_patch')
    rec['BlockRate']       = not acc.get('patch_accepted', True)
    rec['AFSP']            = acc.get('risk_adjusted_success_core')
    rec['FalseBlock']      = gm.get('false_block')
    rec['hidden_test_result'] = hid_res
    rec['public_test_result'] = pub_res
    rec['_recomputed'] = True

    return rec


def main():
    slugs = ['qwen7b', 'qwen14b', 'qwen32b', 'deepseek', 'codellama']
    for slug in slugs:
        path = OUT_DIR / f'r2_{slug}.jsonl'
        if not path.exists():
            print(f'SKIP {slug}: file not found')
            continue
        records = [json.loads(l) for l in open(path)]
        updated = []
        ok = err = 0
        for i, rec in enumerate(records, 1):
            print(f'[{slug}] {i}/{len(records)} {rec["task_id"]}', end=' ', flush=True)
            try:
                rec = recompute_one(rec)
                if '_recompute_error' in rec:
                    err += 1
                    print(f'ERR: {rec["_recompute_error"]}', flush=True)
                else:
                    ok += 1
                    print(f'FuncSucc={rec.get("FuncSucc")} hid={rec.get("hidden_test_result", {}).get("passed", "?")}', flush=True)
            except Exception as e:
                rec['_recompute_error'] = str(e)
                err += 1
                print(f'FATAL: {e}', flush=True)
            updated.append(rec)
        with open(path, 'w') as f:
            for r in updated:
                f.write(json.dumps(r, default=str) + '\n')
        print(f'[{slug}] Done: {ok} ok, {err} errors', flush=True)
    print('ALL DONE', flush=True)


if __name__ == '__main__':
    main()

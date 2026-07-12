"""
Run R2 iterative repair on B3-blocked patches from the canonical 1,200 corpus.

R2 = guard feedback + public test feedback, up to MAX_ITERS repair iterations.
Hidden tests used ONLY for final scoring. Never included in repair prompts.

Usage:
  python pipeline/repair/run_r2_from_corpus.py \\
    --model-slug qwen7b \\
    --llm-url http://localhost:8001/v1 \\
    --out-dir results/G_R2_REPAIR \\
    --max-iters 2

Exits non-zero if fewer than expected records are written.
"""
import argparse
import json
import os
import sys
import shutil
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pipeline.config import is_canonical_run, MODEL_IDS
from pipeline.agent_runner import _parse_files, SYSTEM_PROMPT
from pipeline.patch_applicator import prepare_workdir, apply_patch
from pipeline.dep_extractor import extract_changes, load_requirements
from pipeline.guard.decision import run_guard
from pipeline.test_runner import setup_venv, run_tests
from pipeline.adjudicator.safety_oracle import compute as compute_safety
from pipeline.adjudicator.functional_oracle import compute as compute_functional
from pipeline.adjudicator.metric_calculator import compute as compute_metrics
from pipeline.repair.repair_feedback_builder import build_r2_feedback

import yaml

RESULTS_ROOT = Path('results')
BENCH_ROOT   = Path('bench')

MODEL_SLUG_TO_ID = {
    'qwen7b':    'Qwen2.5-Coder-7B-Instruct',
    'qwen14b':   'Qwen2.5-Coder-14B-Instruct-AWQ',
    'qwen32b':   'Qwen2.5-Coder-32B-Instruct-AWQ',
    'deepseek':  'deepseek-coder-6.7b-instruct',
    'codellama': 'CodeLlama-7b-Instruct-hf',
}

MODEL_ID_TO_SLUG = {v.split('/')[-1]: k for k, v in MODEL_SLUG_TO_ID.items()}
MODEL_ID_TO_SLUG.update({
    'Qwen2.5-Coder-7B-Instruct':    'qwen7b',
    'Qwen2.5-Coder-14B-Instruct-AWQ': 'qwen14b',
    'Qwen2.5-Coder-32B-Instruct-AWQ': 'qwen32b',
    'deepseek-coder-6.7b-instruct':  'deepseek',
    'CodeLlama-7b-Instruct-hf':      'codellama',
})

import glob as _glob


def find_task_dir(task_id: str) -> Path | None:
    for fam_dir in BENCH_ROOT.iterdir():
        p = fam_dir / task_id
        if p.exists():
            return p
    return None


def call_llm(prompt: str, model_id: str, base_url: str) -> dict:
    """Call vLLM server with repair prompt. Returns {files: dict, error: str|None}."""
    import urllib.request as _req
    payload = json.dumps({
        'model': model_id,
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt},
        ],
        'max_tokens': 4096,
        'temperature': 0.0,
    }).encode()
    try:
        req = _req.Request(
            f'{base_url}/chat/completions',
            data=payload,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer token'},
        )
        with _req.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read())
        text = body['choices'][0]['message']['content']
        files = _parse_files(text)
        return {'files': files, 'error': None, 'raw': text[:2000]}
    except Exception as e:
        return {'files': {}, 'error': str(e), 'raw': ''}


def run_r2_one(
    result_json_path: Path,
    model_id: str,
    base_url: str,
    max_iters: int,
    out_dir: Path,
    run_work_base: Path,
) -> dict:
    """Run R2 on one blocked result. Returns metrics dict."""
    with open(result_json_path) as f:
        r = json.load(f)

    task_id = r['task_id']
    cond = r.get('generation_condition', 'G0')
    run_id = uuid.uuid4().hex[:8]
    task_dir = find_task_dir(task_id)
    if task_dir is None:
        return {'error': f'task_dir not found for {task_id}', 'task_id': task_id}

    # Load task metadata (no oracle or hidden-test contents in repair prompts)
    prompt_md = (task_dir / 'prompt.md').read_text()
    evidence_refs = json.loads((task_dir / 'evidence_refs.json').read_text())
    policy = yaml.safe_load((task_dir / 'dependency_policy.yaml').read_text())
    oracle = yaml.safe_load((task_dir / 'risk_oracle.yaml').read_text())
    original_req = load_requirements(task_dir / 'repo')

    # Initial state: original generation guard + public test results
    current_guard = r.get('guard_by_mode', {}).get('B3', {})
    current_public = r.get('public_tests') or {}

    if current_guard.get('decision') != 'BLOCK':
        # Should not happen — only call this for blocked patches
        return {'error': 'not_blocked', 'task_id': task_id}

    iteration_log = []
    final_files = {}
    final_guard = current_guard
    final_public = current_public
    final_hidden = None
    venv_path = None

    work_dir = run_work_base / f'{task_id}_{run_id}'
    work_dir.mkdir(parents=True, exist_ok=True)

    for i in range(max_iters):
        # Build R2 feedback (guard + public tests; NO hidden tests; NO oracle)
        feedback_prompt = build_r2_feedback(
            prompt_md,
            current_guard,
            current_public,
            pip_result=None,
            hidden_test_result=None,  # integrity constraint
        )

        # Call LLM
        llm_out = call_llm(feedback_prompt, model_id, base_url)
        iteration_log.append({
            'iteration': i + 1,
            'llm_error': llm_out.get('error'),
            'files_generated': list(llm_out.get('files', {}).keys()),
        })

        if llm_out.get('error') or not llm_out.get('files'):
            break  # Cannot proceed without a valid patch

        new_files = llm_out['files']
        final_files = new_files

        # Apply to fresh repo copy
        iter_dir = work_dir / f'iter_{i+1}'
        iter_dir.mkdir(parents=True, exist_ok=True)
        repo_dir = prepare_workdir(task_dir, iter_dir)
        apply_patch(new_files, repo_dir)

        # Extract dep changes
        new_req = load_requirements(repo_dir)
        dep_changes = extract_changes(original_req, new_req)

        # Evaluate with B3 guard
        try:
            guard_res = run_guard(dep_changes, evidence_refs, policy, mode='B3')
        except Exception as e:
            guard_res = {'decision': 'ERROR', 'risk_report': [], 'error': str(e)}

        # Run public tests
        try:
            if venv_path is None:
                venv_path = iter_dir / 'venv'
            py_path, _ = setup_venv(venv_path, repo_dir)
            pub_res = run_tests(repo_dir, task_dir / 'tests_public', py_path, label='public')
        except Exception as e:
            pub_res = {'passed': 0, 'failed': 1, 'error': str(e)}

        final_guard = guard_res
        final_public = pub_res
        current_guard = guard_res
        current_public = pub_res

        iteration_log[-1].update({
            'guard_decision': guard_res.get('decision'),
            'pub_passed': pub_res.get('passed', 0),
            'pub_failed': pub_res.get('failed', 0),
        })

        # Stop if unblocked
        if guard_res.get('decision') in ('PASS', 'WARN'):
            break

    # Run hidden tests for final scoring (FINAL SCORING ONLY — never in prompts)
    try:
        final_repo_dir = None
        for i in range(max_iters, 0, -1):
            d = work_dir / f'iter_{i}' / 'repo'
            if d.exists():
                final_repo_dir = d
                break
        if final_repo_dir is None:
            # Repair produced no valid patch; use original repo
            final_repo_dir = Path(result_json_path).parent / 'repo'

        hid_venv = work_dir / 'venv_hidden'
        py_hid, _ = setup_venv(hid_venv, final_repo_dir)
        final_hidden = run_tests(final_repo_dir, task_dir / 'tests_hidden', py_hid, label='hidden')
    except Exception as e:
        final_hidden = {'passed': 0, 'failed': 1, 'error': str(e)}

    # Final dep changes for scoring
    final_req = load_requirements(final_repo_dir) if final_repo_dir and final_repo_dir.exists() else {}
    final_dep_changes = extract_changes(original_req, final_req)

    # Compute metrics
    safety = compute_safety(final_dep_changes, evidence_refs, oracle)
    func   = compute_functional(final_public, final_hidden)
    metrics = compute_metrics(func, safety, final_guard)

    gen = metrics.get('generated', {})
    acc = metrics.get('accepted', {})
    gm  = metrics.get('guard_metrics', {})

    return {
        'task_id': task_id,
        'risk_family': task_id.split('_')[1] if '_' in task_id else '?',
        'model': r.get('model_id', '').split('/')[-1],
        'generation_condition': cond,
        'mode': 'R2',
        'run_id': run_id,
        'num_iterations': len(iteration_log),
        'iteration_log': iteration_log,
        'originally_blocked': True,
        'final_B3_decision': final_guard.get('decision'),
        'FuncSucc':    gen.get('functional_success'),
        'SafetyPassCore': gen.get('safety_pass_core'),
        'RiskyAcc':    acc.get('risky_accepted_patch'),
        'BlockRate':   not acc.get('patch_accepted', True),
        'AFSP':        acc.get('risk_adjusted_success_core'),
        'FalseBlock':  gm.get('false_block'),
        'hidden_test_result': final_hidden,
        'public_test_result': final_public,
    }


def main():
    p = argparse.ArgumentParser(description='Run R2 repair from existing corpus')
    p.add_argument('--model-slug', required=True, choices=list(MODEL_SLUG_TO_ID.keys()),
                   help='Model slug: qwen7b, qwen14b, qwen32b, deepseek, codellama')
    p.add_argument('--llm-url', default='http://localhost:8000/v1')
    p.add_argument('--model-id', default=None,
                   help='Override model_id sent to vLLM API (e.g. model_a if server uses served_model_name)')
    p.add_argument('--out-dir', default='results/G_R2_REPAIR')
    p.add_argument('--max-iters', type=int, default=2)
    p.add_argument('--smoke', action='store_true', help='Run only 2 blocked patches (test mode)')
    args = p.parse_args()

    model_id = args.model_id if args.model_id else MODEL_SLUG_TO_ID[args.model_slug]
    model_name = model_id.split('/')[-1]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_work_base = out_dir / 'workdirs' / args.model_slug
    run_work_base.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f'r2_{args.model_slug}.jsonl'

    # Find already-done (resume support)
    done_tasks = set()
    if out_path.exists():
        with open(out_path) as f:
            for line in f:
                rec = json.loads(line)
                done_tasks.add((rec['task_id'], rec.get('generation_condition')))
        print(f'Already done: {len(done_tasks)}', flush=True)

    # Find all blocked canonical runs for this model
    all_rf = sorted(_glob.glob(str(RESULTS_ROOT / 'task_*' / '*' / 'result.json')))
    blocked = []
    for rf in all_rf:
        run_label = os.path.basename(os.path.dirname(rf))
        if not is_canonical_run(run_label):
            continue
        with open(rf) as f:
            r = json.load(f)
        raw_model = r.get('model_id', '').split('/')[-1]
        if MODEL_ID_TO_SLUG.get(raw_model) != args.model_slug:
            continue
        if r.get('guard_by_mode', {}).get('B3', {}).get('decision') != 'BLOCK':
            continue
        key = (r.get('task_id'), r.get('generation_condition'))
        if key in done_tasks:
            continue
        blocked.append(rf)

    if args.smoke:
        blocked = blocked[:2]

    print(f'Model: {model_name}  Blocked to repair: {len(blocked)}', flush=True)

    ok = 0
    err = 0
    with open(out_path, 'a') as f:
        for i, rf in enumerate(blocked, 1):
            run_label = os.path.basename(os.path.dirname(rf))
            task_id = os.path.basename(os.path.dirname(os.path.dirname(rf)))
            print(f'[{i}/{len(blocked)}] {task_id} {run_label}', end=' ', flush=True)
            try:
                rec = run_r2_one(
                    Path(rf), model_id, args.llm_url, args.max_iters,
                    out_dir, run_work_base,
                )
                if 'error' in rec and rec['error'] not in ('not_blocked',):
                    err += 1
                    print(f'ERR: {rec["error"]}', flush=True)
                else:
                    ok += 1
                    print(f'B3={rec.get("final_B3_decision")} FuncSucc={rec.get("FuncSucc")}', flush=True)
                f.write(json.dumps(rec, default=str) + '\n')
                f.flush()
            except Exception as e:
                err += 1
                print(f'FATAL: {e}', flush=True)

    print(f'\nDone: {ok} ok, {err} errors → {out_path}', flush=True)
    if err > ok and not args.smoke:
        sys.exit(1)


if __name__ == '__main__':
    main()

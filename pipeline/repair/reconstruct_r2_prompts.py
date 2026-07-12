"""
Step 9 artifact recovery: reconstruct the exact R2 repair prompts and run a
contamination audit over them.

WHY THIS EXISTS
---------------
run_r2_from_corpus.py built each repair prompt with build_r2_feedback() but did
NOT persist the prompt text or the raw LLM response text to r2_*.jsonl (only the
parsed file names, guard decision, and pub pass/fail counts were logged). The
final patches DO survive on disk under workdirs/<slug>/<task>_<run>/iter_N/repo.

build_r2_feedback() is a PURE, deterministic function of:
  (prompt.md, guard_result, public_test_result, pip_result=None, hidden=None)
For iteration 1 every input is recoverable from the frozen original result.json
+ the immutable task dir, so the iter-1 prompt is reconstructed byte-exactly.
Iterations >=2 used intermediate guard/test objects that were only summarized in
iteration_log (decision + pass/fail counts, not full risk_report/test details),
so those prompts are reconstructed PARTIALLY and flagged.

CONTAMINATION GUARANTEE (structural, independent of reconstruction):
  run_r2_one() calls build_r2_feedback(..., pip_result=None, hidden_test_result=None)
  and build_r2_feedback() ignores hidden_test_result by construction. No hidden
  test output or risk_oracle content can enter any prompt. This script ALSO
  greps every reconstructed prompt for oracle/hidden-test tokens as a check.

Usage:
  python pipeline/repair/reconstruct_r2_prompts.py
Output:
  results/G_R2_REPAIR/raw_prompts/<slug>/<task>_<cond>/iter_1_prompt.txt
  results/G_R2_REPAIR/raw_prompts/contamination_audit.json
  results/G_R2_REPAIR/raw_prompts/README.md
"""
import json
import os
import sys
import glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import yaml
from pipeline.config import is_canonical_run
from pipeline.repair.repair_feedback_builder import build_r2_feedback

ROOT = Path('.')
RESULTS_ROOT = ROOT / 'results'
BENCH_ROOT = ROOT / 'bench'
OUT_DIR = Path(os.environ.get('OUT_DIR', str(RESULTS_ROOT / 'G_R2_REPAIR')))
RAW_DIR = OUT_DIR / 'raw_prompts'

MODEL_ID_TO_SLUG = {
    'Qwen2.5-Coder-7B-Instruct':      'qwen7b',
    'Qwen2.5-Coder-14B-Instruct-AWQ': 'qwen14b',
    'Qwen2.5-Coder-32B-Instruct-AWQ': 'qwen32b',
    'deepseek-coder-6.7b-instruct':   'deepseek',
    'CodeLlama-7b-Instruct-hf':       'codellama',
}
MODEL_ORDER = ['qwen7b', 'qwen14b', 'qwen32b', 'deepseek', 'codellama']


def find_task_dir(task_id):
    for fam_dir in BENCH_ROOT.iterdir():
        p = fam_dir / task_id
        if p.exists():
            return p
    return None


def build_original_index():
    """(task_id, cond, slug) -> original frozen result.json dict (B3 BLOCK only)."""
    idx = {}
    for rf in sorted(glob.glob(str(RESULTS_ROOT / 'task_*' / '*' / 'result.json'))):
        label = os.path.basename(os.path.dirname(rf))
        if not is_canonical_run(label):
            continue
        try:
            r = json.load(open(rf))
        except Exception:
            continue
        slug = MODEL_ID_TO_SLUG.get(r.get('model_id', '').split('/')[-1])
        if slug is None:
            continue
        if r.get('guard_by_mode', {}).get('B3', {}).get('decision') != 'BLOCK':
            continue
        key = (r.get('task_id'), r.get('generation_condition'), slug)
        idx[key] = r
    return idx


def oracle_tokens(task_dir):
    """Forbidden tokens drawn from risk_oracle.yaml (safe alternatives, versions)."""
    toks = set()
    try:
        oracle = yaml.safe_load((task_dir / 'risk_oracle.yaml').read_text()) or {}
    except Exception:
        return toks

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ('safe_alternative', 'safe_version', 'safe_versions',
                         'recommended', 'fixed_version', 'remediation'):
                    walk(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str) and len(o) >= 4:
            toks.add(o.strip())
    # only collect leaf strings under remediation-ish keys to avoid noise
    rem = []
    def collect(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ('safe_alternative', 'safe_version', 'safe_versions',
                         'recommended', 'fixed_version', 'remediation', 'fix'):
                    if isinstance(v, str):
                        rem.append(v.strip())
                    elif isinstance(v, list):
                        rem.extend([str(x).strip() for x in v if isinstance(x, (str, int, float))])
                collect(v)
        elif isinstance(o, list):
            for v in o:
                collect(v)
    collect(oracle)
    return {t for t in rem if len(t) >= 4}


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    idx = build_original_index()
    print(f'Indexed {len(idx)} originally-blocked result.json records', flush=True)

    audit = {'checked': 0, 'leak_findings': [], 'iter1_reconstructed': 0,
             'iter_ge2_partial': 0, 'missing_original': 0}

    for slug in MODEL_ORDER:
        r2_path = OUT_DIR / f'r2_{slug}.jsonl'
        if not r2_path.exists():
            continue
        with open(r2_path) as f:
            for line in f:
                rec = json.loads(line)
                task_id = rec.get('task_id')
                cond = rec.get('generation_condition')
                key = (task_id, cond, slug)
                orig = idx.get(key)
                if orig is None:
                    audit['missing_original'] += 1
                    continue
                task_dir = find_task_dir(task_id)
                if task_dir is None:
                    audit['missing_original'] += 1
                    continue

                prompt_md = (task_dir / 'prompt.md').read_text()
                guard = orig.get('guard_by_mode', {}).get('B3', {})
                public = orig.get('public_tests') or {}

                # iter-1 prompt: deterministic, byte-exact
                prompt1 = build_r2_feedback(prompt_md, guard, public,
                                            pip_result=None, hidden_test_result=None)

                dst = RAW_DIR / slug / f'{task_id}_{cond}'
                dst.mkdir(parents=True, exist_ok=True)
                (dst / 'iter_1_prompt.txt').write_text(prompt1)

                niter = rec.get('num_iterations', 0)
                audit['iter1_reconstructed'] += 1
                if niter >= 2:
                    audit['iter_ge2_partial'] += 1
                    # leave a marker; full iter>=2 prompt not byte-recoverable
                    (dst / 'iter_2_plus_NOTE.txt').write_text(
                        'Iterations >=2 used intermediate guard/test objects that were '
                        'only summarized in iteration_log (decision + pass/fail counts). '
                        'Full risk_report / test details were not persisted, so the iter>=2 '
                        'prompt body cannot be reconstructed byte-exactly. Structural '
                        'no-leak guarantee still holds (pip_result=None, hidden ignored).\n\n'
                        f'iteration_log: {json.dumps(rec.get("iteration_log", []), indent=2)}\n'
                    )

                # contamination audit over reconstructed prompt
                audit['checked'] += 1
                low = prompt1.lower()
                bad = []
                for marker in ('tests_hidden', 'hidden test', 'risk_oracle',
                               'safe_alternative', 'hidden_test'):
                    if marker in low:
                        bad.append(marker)
                for tok in oracle_tokens(task_dir):
                    if tok.lower() in low and tok.lower() not in prompt_md.lower():
                        # token present in prompt but NOT already in the task's own prompt.md
                        bad.append(f'oracle_token:{tok}')
                if bad:
                    audit['leak_findings'].append({'key': list(key), 'markers': bad})

    (RAW_DIR / 'contamination_audit.json').write_text(json.dumps(audit, indent=2))

    readme = f"""# R2 raw prompts — recovered artifacts (Step 9)

## What is here
- `<slug>/<task>_<cond>/iter_1_prompt.txt` — the **byte-exact** iteration-1 repair
  prompt, reconstructed deterministically from the frozen original `result.json`
  (B3 guard risk_report + public_tests) and the immutable task `prompt.md` via
  `build_r2_feedback()`. temperature=0.0 was used at generation time.
- `<slug>/<task>_<cond>/iter_2_plus_NOTE.txt` — present only where
  `num_iterations >= 2`. The iter>=2 prompt body is **not** byte-recoverable
  because the intermediate guard/test objects were summarized (decision +
  pass/fail) rather than stored in full. The iteration_log is inlined.

## What was NOT persisted by the original run
- **Raw LLM response text** was returned by `call_llm()` (truncated to 2000 chars)
  but discarded — only the parsed file names entered `iteration_log`. The
  **parsed patch files themselves survive** on disk under
  `workdirs/<slug>/<task>_<run>/iter_N/repo` (the applied patch), which is the
  scored artifact. Guard decisions, public-test results, and hidden-test results
  are in `r2_*.jsonl` per record.

## Contamination guarantee
Structural: `run_r2_one()` always calls
`build_r2_feedback(..., pip_result=None, hidden_test_result=None)`, and
`build_r2_feedback()` ignores `hidden_test_result` by construction — hidden tests
and risk_oracle content cannot enter any prompt. `contamination_audit.json`
additionally greps every reconstructed prompt for hidden-test / oracle tokens.

## Audit summary
- prompts checked: {audit['checked']}
- iter-1 reconstructed: {audit['iter1_reconstructed']}
- records with iter>=2 (partial): {audit['iter_ge2_partial']}
- leak findings: {len(audit['leak_findings'])}
- originals not found: {audit['missing_original']}
"""
    (RAW_DIR / 'README.md').write_text(readme)

    print(f"Audit: checked={audit['checked']} "
          f"iter1={audit['iter1_reconstructed']} "
          f"iter>=2_partial={audit['iter_ge2_partial']} "
          f"leaks={len(audit['leak_findings'])} "
          f"missing_orig={audit['missing_original']}", flush=True)
    if audit['leak_findings']:
        print('!!! LEAK FINDINGS:', json.dumps(audit['leak_findings'][:5], indent=2), flush=True)
        sys.exit(1)
    print(f'Wrote prompts + audit → {RAW_DIR}', flush=True)


if __name__ == '__main__':
    main()

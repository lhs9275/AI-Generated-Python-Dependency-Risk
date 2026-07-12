"""
Combine R0/R1 (from extract_r0_r1.py) + R2 (from run_r2_from_corpus.py)
and produce:
  Table A: all-run metrics by model × mode
  Table B: originally-blocked subset metrics
  McNemar test results
"""
import json
import sys
import os
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import csv

try:
    from scipy.stats import chi2
except ImportError:
    chi2 = None

MODEL_ORDER = ['qwen7b', 'qwen14b', 'qwen32b', 'deepseek', 'codellama']
MODEL_DISPLAY = {
    'qwen7b': 'Qwen-7B',
    'qwen14b': 'Qwen-14B',
    'qwen32b': 'Qwen-32B',
    'deepseek': 'DeepSeek-6.7B',
    'codellama': 'CodeLlama-7B',
}
MODEL_ID_TO_SLUG = {
    'Qwen2.5-Coder-7B-Instruct':    'qwen7b',
    'Qwen2.5-Coder-14B-Instruct-AWQ': 'qwen14b',
    'Qwen2.5-Coder-32B-Instruct-AWQ': 'qwen32b',
    'deepseek-coder-6.7b-instruct':  'deepseek',
    'CodeLlama-7b-Instruct-hf':      'codellama',
}

OUT_DIR = Path(os.environ.get('OUT_DIR', 'results/G_R2_REPAIR'))


def load_all_records(out_dir: Path) -> list[dict]:
    records = []
    r0r1 = out_dir / 'r0_r1.jsonl'
    if r0r1.exists():
        with open(r0r1) as f:
            for line in f:
                r = json.loads(line)
                r['model_slug'] = MODEL_ID_TO_SLUG.get(r.get('model', ''), r.get('model', ''))
                records.append(r)
        print(f'Loaded {len(records)} R0/R1 records from {r0r1}', flush=True)

    for slug in MODEL_ORDER:
        r2_path = out_dir / f'r2_{slug}.jsonl'
        if r2_path.exists():
            n = 0
            with open(r2_path) as f:
                for line in f:
                    r = json.loads(line)
                    r['model_slug'] = slug
                    r['mode'] = 'R2'
                    records.append(r)
                    n += 1
            print(f'  R2 {slug}: {n} records', flush=True)

    return records


def safe_pct(num, denom):
    return (num / denom * 100) if denom > 0 else float('nan')


def build_r2_allrun(records: list[dict]) -> list[dict]:
    """Build the R2 *all-run* set (n=240/model) for Table A.

    Per spec: for patches NOT blocked by B3, carry the original patch forward
    for R2 (no LLM call). The r2_*.jsonl files hold only the originally-blocked
    subset; the unblocked remainder is reconstructed here from the R0 records
    (R2==R0 for unblocked patches since the patch is unchanged).

    Carried-forward records get num_iterations=0 so RepairAttemptRate is
    computed over the full benchmark (blocked/total), not the blocked subset.
    """
    r2_blocked = {}
    for r in records:
        if r.get('mode') == 'R2':
            key = (r.get('task_id'), r.get('generation_condition'), r.get('model_slug'))
            r2_blocked[key] = r

    out = list(r2_blocked.values())
    for r in records:
        if r.get('mode') != 'R0':
            continue
        key = (r.get('task_id'), r.get('generation_condition'), r.get('model_slug'))
        if key in r2_blocked:
            continue  # repaired record already included
        cf = dict(r)
        cf['mode'] = 'R2'
        cf['carried_forward'] = True
        cf['num_iterations'] = 0
        out.append(cf)
    return out


def table_a(records: list[dict]) -> list[dict]:
    """Table A: all-run metrics by model × mode (pooled G0+G1).

    R0/R1 already span all 240 runs/model. R2 is expanded to all-run via
    build_r2_allrun (blocked-repaired + carried-forward unblocked).
    """
    r2_allrun = build_r2_allrun(records)
    non_r2 = [r for r in records if r.get('mode') != 'R2']
    records = non_r2 + r2_allrun

    cells = defaultdict(lambda: {'n': 0, 'FuncSucc': 0, 'RiskyAcc': 0,
                                  'BlockRate': 0, 'AFSP': 0, 'FalseBlock': 0,
                                  'RepairAttempt': 0})
    for r in records:
        slug = r.get('model_slug', '?')
        mode = r.get('mode', '?')
        key = (slug, mode)
        c = cells[key]
        c['n'] += 1
        c['FuncSucc']      += 1 if r.get('FuncSucc') else 0
        c['RiskyAcc']      += 1 if r.get('RiskyAcc') else 0
        c['BlockRate']     += 1 if r.get('BlockRate') else 0
        c['AFSP']          += 1 if r.get('AFSP') else 0
        c['FalseBlock']    += 1 if r.get('FalseBlock') else 0
        c['RepairAttempt'] += 1 if r.get('num_iterations', 0) > 0 else 0

    rows = []
    for slug in MODEL_ORDER:
        for mode in ['R0', 'R1', 'R2']:
            key = (slug, mode)
            if key not in cells:
                continue
            c = cells[key]
            n = c['n']
            rows.append({
                'Model': MODEL_DISPLAY.get(slug, slug),
                'Mode': mode,
                'n': n,
                'FuncSucc':          f"{safe_pct(c['FuncSucc'], n):.1f}%",
                'RiskyAcc':          f"{safe_pct(c['RiskyAcc'], n):.1f}%",
                'BlockRate':         f"{safe_pct(c['BlockRate'], n):.1f}%",
                'AFSP_pre_strict':   f"{safe_pct(c['AFSP'], n):.1f}%",
                'FalseBlock':        f"{safe_pct(c['FalseBlock'], n):.1f}%",
                'RepairAttemptRate': f"{safe_pct(c['RepairAttempt'], n):.1f}%" if mode == 'R2' else 'N/A',
                '_n_FuncSucc': c['FuncSucc'],
                '_n_RiskyAcc': c['RiskyAcc'],
                '_n': n,
            })
    return rows


def _build_r1_lookup(records: list[dict]) -> dict:
    """key=(task_id, generation_condition, model) → R1 record."""
    lookup = {}
    for r in records:
        if r.get('mode') == 'R1':
            key = (r.get('task_id'), r.get('generation_condition', ''), r.get('model', ''))
            lookup[key] = r
    return lookup


def table_b(records: list[dict]) -> list[dict]:
    """Table B: originally-blocked subset only."""
    r1_lookup = _build_r1_lookup(records)
    blocked = [r for r in records if r.get('originally_blocked')]
    cells = defaultdict(lambda: {'n': 0, 'StillBlocked': 0, 'FuncSucc': 0,
                                  'RiskyAcc': 0, 'AFSP': 0,
                                  'FuncRegression': 0, 'StillRiskyAccepted': 0,
                                  'ParseFail': 0, 'Timeout': 0})
    for r in blocked:
        slug = r.get('model_slug', '?')
        mode = r.get('mode', '?')
        key = (slug, mode)
        c = cells[key]
        c['n'] += 1
        bd = r.get('final_B3_decision') or r.get('B3_decision', 'BLOCK')
        c['StillBlocked'] += 1 if bd == 'BLOCK' else 0
        c['FuncSucc']     += 1 if r.get('FuncSucc') else 0
        c['RiskyAcc']     += 1 if r.get('RiskyAcc') else 0
        c['AFSP']         += 1 if r.get('AFSP') else 0

        # FuncRegression: this mode FuncSucc=False but R1 FuncSucc=True
        if mode == 'R2':
            r1_key = (r.get('task_id'), r.get('generation_condition', ''), r.get('model', ''))
            r1 = r1_lookup.get(r1_key)
            if r1 and bool(r1.get('FuncSucc')) and not bool(r.get('FuncSucc')):
                c['FuncRegression'] += 1

        # StillRiskyAccepted: patch accepted (not blocked) but RiskyAcc
        if r.get('RiskyAcc') and bd != 'BLOCK':
            c['StillRiskyAccepted'] += 1

        # ParseFail / Timeout from iteration_log llm_error
        for it in r.get('iteration_log', []):
            err = str(it.get('llm_error', '') or '').lower()
            if err:
                if 'parse' in err or 'json' in err or 'extract' in err:
                    c['ParseFail'] += 1
                elif 'timeout' in err or 'timed out' in err:
                    c['Timeout'] += 1

    rows = []
    for slug in MODEL_ORDER:
        for mode in ['R1', 'R2']:
            key = (slug, mode)
            if key not in cells:
                continue
            c = cells[key]
            n = c['n']
            rows.append({
                'Model': MODEL_DISPLAY.get(slug, slug),
                'Mode': mode,
                'n_blocked':          n,
                'StillBlocked':       f"{safe_pct(c['StillBlocked'], n):.1f}%",
                'RepairSuccess':      f"{safe_pct(n - c['StillBlocked'], n):.1f}%",
                'FuncSucc':           f"{safe_pct(c['FuncSucc'], n):.1f}%",
                'AFSP':               f"{safe_pct(c['AFSP'], n):.1f}%",
                'FuncRegression':     f"{safe_pct(c['FuncRegression'], n):.1f}%" if mode == 'R2' else 'N/A',
                'StillRiskyAccepted': f"{safe_pct(c['StillRiskyAccepted'], n):.1f}%",
                'ParseFail':          f"{safe_pct(c['ParseFail'], n):.1f}%" if mode == 'R2' else 'N/A',
                'Timeout':            f"{safe_pct(c['Timeout'], n):.1f}%" if mode == 'R2' else 'N/A',
            })
    return rows


def mcnemar(a: int, b: int, c: int, d: int) -> float:
    """McNemar exact mid-p approximation (chi^2 with continuity correction)."""
    denom = b + c
    if denom == 0:
        return 1.0
    stat = (abs(b - c) - 1) ** 2 / denom if abs(b - c) >= 1 else 0.0
    if chi2 is None:
        return float('nan')
    from scipy.stats import chi2 as _chi2
    return float(1 - _chi2.cdf(stat, df=1))


def mcnemar_tests(records: list[dict]) -> list[dict]:
    """Paired McNemar: R1 vs R2 on FuncSucc and AFSP, per model."""
    # Match records by (task_id, generation_condition, model_slug)
    by_key = defaultdict(dict)
    for r in records:
        key = (r.get('task_id'), r.get('generation_condition'), r.get('model_slug'))
        mode = r.get('mode')
        if mode in ('R1', 'R2'):
            by_key[key][mode] = r

    results = []
    for metric in ('FuncSucc', 'AFSP', 'RiskyAcc'):
        slug_pairs = defaultdict(lambda: {'b': 0, 'c': 0, 'n': 0})
        for key, modes in by_key.items():
            if 'R1' not in modes or 'R2' not in modes:
                continue
            slug = key[2]
            r1 = bool(modes['R1'].get(metric))
            r2 = bool(modes['R2'].get(metric))
            slug_pairs[slug]['n'] += 1
            if not r1 and r2:
                slug_pairs[slug]['b'] += 1  # R2 better
            elif r1 and not r2:
                slug_pairs[slug]['c'] += 1  # R1 better

        for slug in MODEL_ORDER:
            if slug not in slug_pairs:
                continue
            sp = slug_pairs[slug]
            p = mcnemar(0, sp['b'], sp['c'], 0)
            # Polarity-neutral counts: b = metric True in R2 & False in R1; c = vice
            # versa. For FuncSucc/AFSP True is good (b favors R2); for RiskyAcc True
            # is BAD (b means R2 newly-risky). 'favors' is polarity-aware.
            higher_is_better = metric in ('FuncSucc', 'AFSP')
            if sp['b'] == sp['c']:
                favors = 'tie'
            elif higher_is_better:
                favors = 'R2' if sp['b'] > sp['c'] else 'R1'
            else:  # RiskyAcc: more True = worse
                favors = 'R1' if sp['b'] > sp['c'] else 'R2'
            results.append({
                'Model': MODEL_DISPLAY.get(slug, slug),
                'Metric': metric,
                'n_paired': sp['n'],
                'R2_True_R1_False': sp['b'],
                'R1_True_R2_False': sp['c'],
                'favors': favors if (p == p and p < 0.05) else '',
                'McNemar_p': f'{p:.4f}' if p == p else 'N/A',
                'sig': '*' if (p == p and p < 0.05) else '',
                'primary_case': 'yes' if slug in ('qwen7b', 'qwen32b') else 'no',
            })
    return results


def write_csv(rows: list[dict], path: Path):
    if not rows:
        print(f'  [SKIP] no rows for {path.name}')
        return
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=[k for k in rows[0].keys() if not k.startswith('_')])
        w.writeheader()
        for row in rows:
            w.writerow({k: v for k, v in row.items() if not k.startswith('_')})
    print(f'  Wrote {len(rows)} rows → {path}')


def record_environment(out_dir: Path):
    """Record git, python, pip, vLLM version into out_dir/environment.txt."""
    import subprocess
    lines = []
    for cmd in [
        ['git', 'log', '--oneline', '-1'],
        ['git', 'status', '--short'],
        ['python3', '--version'],
        ['nvidia-smi'],
        ['python3', '-c', 'import vllm; print("vllm", vllm.__version__)'],
        ['pip', 'freeze'],
    ]:
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT,
                                          cwd=str(Path(__file__).resolve().parents[2])).decode()
            lines.append(f'=== {" ".join(cmd)} ===\n{out}')
        except Exception as e:
            lines.append(f'=== {" ".join(cmd)} === ERROR: {e}\n')

    # vLLM version: this CPU table-build env has no vllm; the servers ran in a
    # separate GPU env. Set VLLM_DISTINFO_GLOB to that env's vllm-*.dist-info
    # to record the exact served version.
    import glob as _g, os as _os
    vllm_note = 'vLLM version: not importable in this CPU build env.\n'
    for di in sorted(_g.glob(_os.environ.get('VLLM_DISTINFO_GLOB', '') or '/nonexistent/*')):
        ver = Path(di).name.replace('vllm-', '').replace('.dist-info', '')
        vllm_note += (f'vLLM (GPU server env that served the models): '
                      f'{ver}  [source: {di}]\n')
        break
    lines.append(f'=== vLLM version (server env) ===\n{vllm_note}')

    # Provenance + recovered-artifact notes (kept inside the function so they
    # survive every regeneration of environment.txt).
    lines.append(
        '=== NOTES ===\n'
        'directory naming: spec requested results/G_R2_REPAIR_<timestamp>/ but this\n'
        '  single run used results/G_R2_REPAIR/ (no collision risk).\n'
        'raw prompts/responses (spec step 9): run_r2_from_corpus.py did not persist\n'
        '  prompt/response TEXT to r2_*.jsonl. iter-1 prompts are reconstructed\n'
        '  byte-exactly into raw_prompts/ by reconstruct_r2_prompts.py (build_r2_feedback\n'
        '  is a pure deterministic fn of frozen result.json + immutable task dir).\n'
        '  iter>=2 prompt bodies are not byte-recoverable (intermediate guard/test\n'
        '  objects were only summarized). Final patches survive under workdirs/.../iter_N/repo.\n'
        '  No-leak guarantee is structural (pip_result=None, hidden_test_result ignored)\n'
        '  and confirmed by raw_prompts/contamination_audit.json (0 leaks / 306 prompts).\n'
    )

    env_path = out_dir / 'environment.txt'
    env_path.write_text('\n'.join(lines))
    print(f'  Wrote environment → {env_path}')


def main():
    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    record_environment(out_dir)

    records = load_all_records(out_dir)
    print(f'Total records: {len(records)}')

    ta = table_a(records)
    tb = table_b(records)
    mc = mcnemar_tests(records)

    write_csv(ta, out_dir / 'table_A_all_runs.csv')
    write_csv(tb, out_dir / 'table_B_blocked_subset.csv')
    write_csv(mc, out_dir / 'mcnemar_r1_vs_r2.csv')

    # Print summary
    print('\n=== Table A: All runs (model × mode) ===')
    print(f'{"Model":<20} {"Mode":<5} {"n":<6} {"FuncSucc":<10} {"RiskyAcc":<10} {"BlockRate":<10} {"AFSP_pre_strict":<16} {"FalseBlock":<11} {"RepairAttemptRate":<18}')
    for row in ta:
        print(f'{row["Model"]:<20} {row["Mode"]:<5} {row["n"]:<6} {row["FuncSucc"]:<10} {row["RiskyAcc"]:<10} {row["BlockRate"]:<10} {row["AFSP_pre_strict"]:<16} {row["FalseBlock"]:<11} {row["RepairAttemptRate"]:<18}')

    print('\n=== Table B: Blocked subset ===')
    print(f'{"Model":<20} {"Mode":<5} {"n_blk":<7} {"StillBlocked":<14} {"RepairSucc":<12} {"FuncSucc":<10} {"AFSP":<10} {"FuncRegression":<15} {"StillRiskyAcc":<14} {"ParseFail":<10} {"Timeout":<8}')
    for row in tb:
        print(f'{row["Model"]:<20} {row["Mode"]:<5} {row["n_blocked"]:<7} {row["StillBlocked"]:<14} {row["RepairSuccess"]:<12} {row["FuncSucc"]:<10} {row["AFSP"]:<10} {row["FuncRegression"]:<15} {row["StillRiskyAccepted"]:<14} {row["ParseFail"]:<10} {row["Timeout"]:<8}')

    print('\n=== McNemar R1 vs R2 ===')
    for row in mc:
        print(f'{row["Model"]:<20} {row["Metric"]:<12} n={row["n_paired"]} '
              f'p={row["McNemar_p"]} {row["sig"]:<2} {("favors "+row["favors"]) if row["favors"] else ""}')


if __name__ == '__main__':
    main()

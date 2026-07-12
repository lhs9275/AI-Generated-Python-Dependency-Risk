#!/usr/bin/env python3
"""Batch score all agentic run manifests in parallel."""
import json
import sys
import os
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, '.')

MANIFEST_IN  = Path('data/agentic/runs_model_d_final_v2.jsonl')
MANIFEST_OUT = Path('data/agentic/runs_model_d_scored.jsonl')
BENCH_DIR    = Path('bench')
WORKERS      = int(os.environ.get('WORKERS', '4'))


def find_task_dir(bench_dir: Path, task_id: str) -> Path:
    matches = list(bench_dir.glob(f'*/{task_id}'))
    if not matches:
        raise FileNotFoundError(f'No task dir for {task_id}')
    return matches[0]


def score_one(record: dict) -> dict:
    from pipeline.agentic.score_agentic_outputs import score_run
    task_dir = find_task_dir(BENCH_DIR, record['task_id'])
    work_dir = Path(record['final_patch_path']).parent
    try:
        return score_run(record, task_dir, work_dir)
    except Exception as e:
        record['scoring_error'] = str(e)
        return record


def main():
    records = []
    with open(MANIFEST_IN) as f:
        for l in f:
            records.append(json.loads(l))

    # Resume: skip already scored
    done_ids = set()
    if MANIFEST_OUT.exists():
        with open(MANIFEST_OUT) as f:
            for l in f:
                r = json.loads(l)
                done_ids.add((r['task_id'], r.get('condition'), r.get('run_id')))
        print(f'Already scored: {len(done_ids)}', flush=True)

    todo = [r for r in records
            if (r['task_id'], r.get('condition'), r.get('run_id')) not in done_ids]
    print(f'To score: {len(todo)} / {len(records)} (workers={WORKERS})', flush=True)

    scored = 0
    errors = 0

    with open(MANIFEST_OUT, 'a') as out_f:
        with ProcessPoolExecutor(max_workers=WORKERS) as ex:
            futs = {ex.submit(score_one, r): r for r in todo}
            for i, fut in enumerate(as_completed(futs), 1):
                orig = futs[fut]
                try:
                    result = fut.result()
                    if 'scoring_error' in result:
                        errors += 1
                        tid = orig['task_id']
                        cond = orig['condition'][:20]
                        err = result['scoring_error']
                        print(f'[{i}/{len(todo)}] {tid} {cond} ERR: {err}', flush=True)
                    else:
                        scored += 1
                        tid = orig['task_id']
                        cond = orig['condition'][:30]
                        b3 = result.get('B3_score', '?')
                        func = result.get('FuncSucc', '?')
                        print(f'[{i}/{len(todo)}] {tid} {cond} B3={b3} FuncSucc={func}', flush=True)
                    out_f.write(json.dumps(result, default=str) + '\n')
                    out_f.flush()
                except Exception as e:
                    errors += 1
                    fatal_tid = orig['task_id']
                    print(f'[{i}/{len(todo)}] {fatal_tid} FATAL: {e}', flush=True)

    print(f'\nDone: {scored} scored, {errors} errors', flush=True)

    # Summary table
    from collections import defaultdict
    stats = defaultdict(lambda: {'n':0,'FuncSucc':0,'RiskyAcc':0,'DIR':0,'AFSP':0})
    with open(MANIFEST_OUT) as f:
        for l in f:
            r = json.loads(l)
            c = r.get('condition','?')
            s = stats[c]
            s['n'] += 1
            s['FuncSucc'] += bool(r.get('FuncSucc'))
            s['RiskyAcc'] += bool(r.get('RiskyAcc'))
            s['DIR'] += bool(r.get('DIR'))
            s['AFSP'] += bool(r.get('AFSP'))

    print()
    print(f'{"Condition":<45} n    FuncSucc  RiskyAcc  DIR   AFSP')
    for c in sorted(stats.keys()):
        s = stats[c]
        n = s['n']
        print(f'{c:<45} {n:<5}{s["FuncSucc"]/n:.2%}    {s["RiskyAcc"]/n:.2%}    {s["DIR"]/n:.2%}  {s["AFSP"]/n:.2%}')


if __name__ == '__main__':
    main()

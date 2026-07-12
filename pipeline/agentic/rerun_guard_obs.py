#!/usr/bin/env python3
"""Rerun failed guard_observation tasks using existing infrastructure."""
import json
import sys
import os

sys.path.insert(0, '.')

from pathlib import Path
from pipeline.agentic.run_agentic_tasks import run_task

FAILED_TASKS_FILE = 'data/agentic/guard_obs_failed_tasks.json'
BENCH_DIR = Path('bench')
OUTPUT_FILE = Path('data/agentic/guard_obs_rerun.jsonl')
RESULTS_DIR = Path('results/agentic/model_d_final')
VLLM_BASE_URL = 'http://localhost:8001/v1'
MODEL_NAME = 'model_d'

with open(FAILED_TASKS_FILE) as f:
    failed_task_ids = set(json.load(f))

print(f'Tasks to rerun: {len(failed_task_ids)}', flush=True)

# Check existing output (resume)
already_done = set()
if OUTPUT_FILE.exists():
    with open(OUTPUT_FILE) as f:
        for l in f:
            r = json.loads(l)
            already_done.add(r['task_id'])
    print(f'Already done: {len(already_done)}', flush=True)

# Find task dirs
task_dirs = {}
for task_dir in BENCH_DIR.glob('*/task_*'):
    task_dirs[task_dir.name] = task_dir

tasks_to_run = [t for t in sorted(failed_task_ids) if t not in already_done]
print(f'Remaining: {len(tasks_to_run)}', flush=True)

ok = 0
fail = 0

with open(OUTPUT_FILE, 'a') as out_f:
    for i, task_id in enumerate(tasks_to_run, 1):
        if task_id not in task_dirs:
            print(f'[{i}/{len(tasks_to_run)}] {task_id} ... NOT FOUND in bench', flush=True)
            continue

        task_dir = task_dirs[task_id]
        print(f'[{i}/{len(tasks_to_run)}] {task_id} ... ', end='', flush=True)

        try:
            manifest = run_task(
                task_dir=task_dir,
                model_id=MODEL_NAME,
                condition='agent_with_guard_observation',
                results_dir=RESULTS_DIR,
                max_turns=10,
                seed=42,
                llm_base_url=VLLM_BASE_URL,
            )
            fm = manifest.get('failure_mode') or 'none'
            turns = manifest.get('num_turns', 0)
            print(f'{fm} ({turns} turns)', flush=True)
            if not fm or fm in ('none', 'ok'):
                ok += 1
            else:
                fail += 1
            out_f.write(json.dumps(manifest, default=str) + '\n')
            out_f.flush()
        except Exception as e:
            print(f'ERROR: {e}', flush=True)
            fail += 1

print(f'\nDone: {ok} ok, {fail} failed', flush=True)
print(f'Output: {OUTPUT_FILE}', flush=True)

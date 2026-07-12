#!/usr/bin/env python3
import json, sys
sys.path.insert(0, '.')
from pathlib import Path
from pipeline.agentic.run_agentic_tasks import run_task

BENCH_DIR = Path('bench')
RESULTS_DIR = Path('results/agentic/model_d_final')
OUTPUT = Path('data/agentic/guard_obs_missing.jsonl')

task_id = 'task_F3_005'
task_dir = next(BENCH_DIR.glob(f'*/task_F3_005'))

print(f'Running {task_id}...', flush=True)
manifest = run_task(
    task_dir=task_dir,
    model_id='model_d',
    condition='agent_with_guard_observation',
    results_dir=RESULTS_DIR,
    max_turns=10,
    seed=42,
    llm_base_url='http://localhost:8001/v1',
)
print(f"Done: {manifest.get('failure_mode') or 'none'} ({manifest.get('num_turns',0)} turns)", flush=True)
with open(OUTPUT, 'w') as f:
    f.write(json.dumps(manifest, default=str) + '\n')

#!/bin/bash
# Idempotent driver: finish all incomplete E1a-U2U3 legs (gen->gate->score).
# gen resumes via runner's task_id skip; gate/score are pure (re)runs. Login-node CPU
# for gate/score; GPU only for the two legs still needing generation.
set -u
cd .
export PYTHONPATH="$(pwd)${PYTHONPATH:+:$PYTHONPATH}"  # run_gate_ladder does `import pipeline`
source <CONDA>/etc/profile.d/conda.sh; conda activate <ENV>
PY=python
RUN=pipeline/e1a_agentic_sweep/e1a_run_pr_tasks.py
GATE=pipeline/tse_gap_closure/run_gate_ladder.py
SCORE=pipeline/e1a_agentic_sweep/e1a_score_independent.py
TASKS=results/e1a_pr_tasks/tasks.jsonl
ROOT=results/e1a_pr_gen
N=$(wc -l < "$TASKS")

# model -> served-name|endpoint|modelpath  (gen only where needed)
declare -A EP=(
  [deepseek6b]="http://localhost:8000/v1|deepseek6b"
  [qwen32b]="http://localhost:8000/v1|qwen32b"
)

gen() { # tag cond
  local tag=$1 c=$2 dir=$ROOT/$1/$2 g=$ROOT/$1/$2/generated_changes.jsonl
  local have=0; [ -f "$g" ] && have=$(wc -l < "$g")
  if [ "$have" -ge "$N" ]; then echo "[gen] $tag/$c complete ($have)"; return 0; fi
  IFS='|' read -r ep mp <<< "${EP[$tag]}"
  echo "[gen] $tag/$c $have/$N -> resume @ $ep"
  $PY $RUN --tasks $TASKS --model "$mp" --tag "$tag" --condition "$c" --endpoint "$ep"
}
gate() { # tag cond
  local dir=$ROOT/$1/$2 g=$ROOT/$1/$2/generated_changes.jsonl o=$ROOT/$1/$2/guard_outputs.jsonl
  local have=0; [ -f "$o" ] && have=$(wc -l < "$o")
  local gn=0; [ -f "$g" ] && gn=$(wc -l < "$g")
  if [ "$have" -ge "$gn" ] && [ "$gn" -gt 0 ]; then echo "[gate] $1/$2 complete ($have)"; return 0; fi
  echo "[gate] $1/$2 -> run"
  $PY $GATE --patches "$g" --out "$o"
}
score() { # tag cond
  local dir=$ROOT/$1/$2 s=$ROOT/$1/$2/e1a_independent_summary.json
  echo "[score] $1/$2 -> run"
  $PY $SCORE --generated $ROOT/$1/$2/generated_changes.jsonl \
             --gate $ROOT/$1/$2/guard_outputs.jsonl --out-dir "$dir"
}

# --- legs needing generation first (GPU) ---
gen deepseek6b safety_prompt
gen qwen32b agent_native
gen qwen32b safety_prompt

# --- gate+score every leg that has full generation ---
for tag in qwen7b qwen14b deepseek6b codellama7b qwen32b; do
  for c in agent_native safety_prompt; do
    g=$ROOT/$tag/$c/generated_changes.jsonl
    [ -f "$g" ] || { echo "[skip] $tag/$c no gen"; continue; }
    [ "$(wc -l < "$g")" -ge "$N" ] || { echo "[skip] $tag/$c gen incomplete"; continue; }
    gate "$tag" "$c"
    score "$tag" "$c"
  done
done
echo "=== DRIVER DONE $(date -u) ==="

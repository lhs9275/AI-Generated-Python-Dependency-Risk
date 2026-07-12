#!/bin/bash
# Usage: sbatch --export=MODEL_SLUG=qwen7b,LLM_URL=http://localhost:8001/v1 sbatch_r2_repair.sh
#SBATCH --job-name=asg-r2
#SBATCH --partition=batch
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=05:00:00
#SBATCH --output=logs/repair_r2_%x_%j.log
#SBATCH --error=logs/repair_r2_%x_%j.err
#SBATCH --chdir=.

export PATH=<PYENV>/bin:$PATH
export OUT_DIR=results/G_R2_REPAIR

mkdir -p logs results/G_R2_REPAIR

echo "=== MODEL_SLUG=${MODEL_SLUG}  LLM_URL=${LLM_URL} ===" ; date

# Wait up to 5 minutes for the vLLM server to be ready
for i in $(seq 1 30); do
    if curl -sf "${LLM_URL}/models" > /dev/null 2>&1; then
        echo "vLLM server ready at ${LLM_URL}"
        break
    fi
    echo "Waiting for vLLM server... (${i}/30)"
    sleep 10
done

MODEL_ID_ARG=""
if [ -n "${MODEL_ID:-}" ]; then
    MODEL_ID_ARG="--model-id ${MODEL_ID}"
fi

python pipeline/repair/run_r2_from_corpus.py \
    --model-slug "${MODEL_SLUG}" \
    --llm-url "${LLM_URL}" \
    ${MODEL_ID_ARG} \
    --out-dir results/G_R2_REPAIR \
    --max-iters 2

echo "=== DONE ===" ; date

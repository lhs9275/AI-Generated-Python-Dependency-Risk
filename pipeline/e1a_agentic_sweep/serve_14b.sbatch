#!/bin/bash
#SBATCH --job-name=<ANON_ID>-asg-e1a-serve-14b
#SBATCH --partition=batch
# #SBATCH --nodelist=<gpu-node>   # optional: pin to a GPU node
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --output=results/e1a_pr_gen/serve_14b_%j.log
echo "NODE=$(hostname) JOB=$SLURM_JOB_ID $(date -u)"
source <CONDA>/etc/profile.d/conda.sh; conda activate <ENV>
# model-specific vLLM flags (14B-AWQ: awq_marlin, enforce-eager, no prefix caching)
python -m vllm.entrypoints.openai.api_server \
  --model Qwen2.5-Coder-14B-Instruct-AWQ \
  --served-model-name qwen14b --quantization awq_marlin \
  --max-model-len 8192 --gpu-memory-utilization 0.6 --enforce-eager --no-enable-prefix-caching \
  --host 0.0.0.0 --port 8000

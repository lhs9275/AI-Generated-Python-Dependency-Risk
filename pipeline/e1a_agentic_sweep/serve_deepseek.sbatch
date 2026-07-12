#!/bin/bash
#SBATCH --job-name=<ANON_ID>-asg-e1a-serve-deepseek
#SBATCH --partition=batch
# #SBATCH --nodelist=<gpu-node>   # optional: pin to a GPU node
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --output=results/e1a_pr_gen/serve_deepseek_%j.log
echo "NODE=$(hostname) JOB=$SLURM_JOB_ID $(date -u)"
source <CONDA>/etc/profile.d/conda.sh; conda activate <ENV>
# model-specific vLLM flags (deepseek: trust-remote-code, no prefix caching)
python -m vllm.entrypoints.openai.api_server \
  --model deepseek-coder-6.7b-instruct \
  --served-model-name deepseek6b --trust-remote-code \
  --max-model-len 8192 --gpu-memory-utilization 0.74 --no-enable-prefix-caching \
  --host 0.0.0.0 --port 8000

#!/bin/bash
#SBATCH --job-name=<ANON_ID>-asg-e1a-serve-32b
#SBATCH --partition=batch
# #SBATCH --nodelist=<gpu-node>   # optional: pin to a GPU node
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --output=results/e1a_pr_gen/serve_32b_%j.log
echo "NODE=$(hostname) JOB=$SLURM_JOB_ID $(date -u)"
source <CONDA>/etc/profile.d/conda.sh; conda activate <ENV>
# model-specific vLLM flags (32B-AWQ: awq_marlin, enforce-eager; served on an RTX 5090)
python -m vllm.entrypoints.openai.api_server \
  --model Qwen2.5-Coder-32B-Instruct-AWQ \
  --served-model-name qwen32b --quantization awq_marlin \
  --max-model-len 8192 --gpu-memory-utilization 0.74 --enforce-eager \
  --host 0.0.0.0 --port 8000

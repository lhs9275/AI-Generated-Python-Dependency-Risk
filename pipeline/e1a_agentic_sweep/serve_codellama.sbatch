#!/bin/bash
#SBATCH --job-name=<ANON_ID>-asg-e1a-serve-codellama
#SBATCH --partition=batch
# #SBATCH --nodelist=<gpu-node>   # optional: pin to a GPU node
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=03:00:00
#SBATCH --output=results/e1a_pr_gen/serve_codellama_%j.log
echo "NODE=$(hostname) JOB=$SLURM_JOB_ID $(date -u)"
source <CONDA>/etc/profile.d/conda.sh; conda activate <ENV>
# model-specific vLLM flags (CodeLlama: full bf16, no prefix caching)
python -m vllm.entrypoints.openai.api_server \
  --model CodeLlama-7b-Instruct-hf \
  --served-model-name codellama7b \
  --max-model-len 8192 --gpu-memory-utilization 0.74 --no-enable-prefix-caching \
  --host 0.0.0.0 --port 8000

#!/bin/bash
#SBATCH --job-name=<ANON_ID>-asg-e1a-serve7b
#SBATCH --partition=batch
#SBATCH --gres=gpu:1
# #SBATCH --nodelist=<gpu-node>   # optional: pin to a GPU node
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --output=results/e1a_pr_gen/serve7b_%j.log

# vLLM OpenAI server for E1a generation. 7B served with --dtype bfloat16 (no
# quantization; runtime caps gpu-mem at 0.74). Bind 0.0.0.0 so the
# login-node runner can reach it at http://$(hostname):8000/v1.
echo "NODE=$(hostname)  JOB=$SLURM_JOB_ID  $(date -u)"
source <CONDA>/etc/profile.d/conda.sh
conda activate <ENV>
echo "python=$(which python)"
python -c "import vllm; print('vllm', vllm.__version__)"
export VLLM_LOGGING_LEVEL=INFO
# Match the ORIGINAL experiment: --dtype bfloat16, NO quantization
# for the <=13B full models (7B/6.7B/CodeLlama). Quantizing here (e.g. bitsandbytes)
# would change the model vs the single-pass baseline and break comparability.
python -m vllm.entrypoints.openai.api_server \
  --model Qwen2.5-Coder-7B-Instruct \
  --served-model-name qwen7b \
  --dtype bfloat16 \
  --gpu-memory-utilization 0.74 \
  --max-model-len 8192 \
  --host 0.0.0.0 --port 8000

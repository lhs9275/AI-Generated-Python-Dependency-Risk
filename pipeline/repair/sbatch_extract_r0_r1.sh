#!/bin/bash
#SBATCH --job-name=asg-r0r1
#SBATCH --partition=batch
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=logs/repair_r0r1_%j.log
#SBATCH --error=logs/repair_r0r1_%j.err
#SBATCH --chdir=.

export PATH=<PYENV>/bin:$PATH
export OUT_DIR=results/G_R2_REPAIR

mkdir -p logs results/G_R2_REPAIR

# Record environment
echo "=== GIT ===" ; git log -1 --oneline
echo "=== PYTHON ===" ; python --version
echo "=== START ===" ; date

python pipeline/repair/extract_r0_r1.py

echo "=== DONE ===" ; date

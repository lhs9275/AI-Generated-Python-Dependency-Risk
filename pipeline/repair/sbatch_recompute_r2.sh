#!/bin/bash
#SBATCH --job-name=asg-r2-recompute
#SBATCH --partition=batch
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=logs/recompute_r2_%j.log
#SBATCH --error=logs/recompute_r2_%j.err
#SBATCH --chdir=.

export PATH=<PYENV>/bin:$PATH

echo "=== START ===" ; date
python pipeline/repair/recompute_r2_tests.py
echo "=== DONE ===" ; date

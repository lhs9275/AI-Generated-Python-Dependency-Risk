#!/bin/bash
#SBATCH --job-name=asg-score
#SBATCH --partition=batch
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=logs/batch_score_%j.log
#SBATCH --error=logs/batch_score_%j.err
#SBATCH --chdir=.

export PATH=<PYENV>/bin:$PATH
export WORKERS=8

python pipeline/agentic/batch_score.py

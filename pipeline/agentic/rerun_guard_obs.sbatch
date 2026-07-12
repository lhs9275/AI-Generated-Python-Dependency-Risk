#!/bin/bash
#SBATCH --job-name=guard-obs-rerun
#SBATCH --partition=batch
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=logs/guard_obs_rerun_%j.log
#SBATCH --error=logs/guard_obs_rerun_%j.err
#SBATCH --chdir=.

export PATH=<PYENV>/bin:$PATH

mkdir -p logs

python pipeline/agentic/rerun_guard_obs.py

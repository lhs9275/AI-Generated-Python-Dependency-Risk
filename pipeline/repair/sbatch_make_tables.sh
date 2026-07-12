#!/bin/bash
#SBATCH --job-name=asg-repair-tables
#SBATCH --partition=batch
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=logs/repair_tables_%j.log
#SBATCH --error=logs/repair_tables_%j.err
#SBATCH --chdir=.

export PATH=<PYENV>/bin:$PATH
export OUT_DIR=results/G_R2_REPAIR

echo "=== START ===" ; date
python pipeline/repair/make_repair_tables.py
echo "=== DONE ===" ; date

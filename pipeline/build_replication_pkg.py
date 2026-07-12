"""
Replication package builder for AgentSupplyGuard.

Produces a self-contained ZIP suitable for anonymous upload to
Zenodo / 4open.science.  The archive is named:
    agentsupplyguard-replication-<sha8>.zip

Included:
  bench/           -- all 120 tasks WITH tests_hidden/ (oracle needed for replication)
  pipeline/        -- all analysis + guard scripts
  results/         -- aggregated JSON + every per-run result.json (the raw
                      task-level outputs that build_tables.py / compute_tse_stats.py
                      / reproduce_tables.py consume). Heavy per-run working dirs
                      (venv/, repo/, patches) are pruned -- only result.json is kept.
  evaluation/manual_audit/ -- manual audit sheets, rating rubric, IRR script/report
  research_notes/figures/  -- PDF + PNG figures
  paper/en/main.pdf        -- final compiled PDF
  requirements.txt
  README-replication.md

Excluded (double-blind / size):
  .git/
  results/task_*/**/venv/, repo/   -- per-run working dirs (huge; not needed)
  _sbatch_*.sh             -- cluster-specific scripts
  __pycache__/, *.pyc
  *.log, *.aux, *.blg      -- LaTeX build artifacts
  paper/ko/                -- Korean internal mirror (not submitted)
  research_notes/findings/ -- internal lab notes

Usage:
    python pipeline/build_replication_pkg.py [--out-dir .]
"""

import argparse
import hashlib
import os
import shutil
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

INCLUDE_RULES: list[tuple[str, list[str]]] = [
    ("bench",                   []),
    ("pipeline",                ["__pycache__", "*.pyc"]),
    # task_* full trees are pruned here (heavy venv/repo working dirs); the
    # small per-run result.json files are added separately by add_result_jsons().
    ("results",                 ["task_*"]),
    ("evaluation/manual_audit", ["__pycache__", "*.pyc"]),
    ("research_notes/figures",  []),
    ("paper/en",                ["*.aux", "*.log", "*.out", "*.toc",
                                  "*.blg", "*.bbl", "*.synctex.gz",
                                  "*.fls", "*.fdb_latexmk", ".tectonic"]),
    ("requirements.txt",        []),
    ("README-replication.md",   []),
]

SKIP_NAMES = {"__pycache__", ".git", ".tectonic", ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".log", ".aux", ".blg", ".bbl",
                 ".synctex.gz", ".fls", ".fdb_latexmk"}


def _should_skip(path: Path, excludes: list[str]) -> bool:
    if path.name in SKIP_NAMES:
        return True
    if path.suffix in SKIP_SUFFIXES:
        return True
    for pat in excludes:
        if path.match(pat):
            return True
    return False


def collect_files(src: Path, excludes: list[str]) -> list[Path]:
    if src.is_file():
        return [src]
    files = []
    # Walk top-down and PRUNE excluded directories in place so we never descend
    # into them. rglob("*") would eagerly materialize every path under src first
    # (incl. results/task_*/**/venv/ — hundreds of thousands of files), which
    # exhausts memory and gets the process SIGKILL'd before any filtering runs.
    for root, dirs, filenames in os.walk(src, followlinks=False):
        root_path = Path(root)
        dirs[:] = sorted(
            d for d in dirs if not _should_skip(root_path / d, excludes)
        )
        for fn in sorted(filenames):
            p = root_path / fn
            if p.is_file() and not _should_skip(p, excludes):
                files.append(p)
    return files


def collect_result_jsons(results_root: Path) -> list[Path]:
    """Yield only the per-run result.json files under results/task_*/.

    These are the raw task-level outputs that build_tables.py,
    compute_tse_stats.py and reproduce_tables.py consume. The sibling
    working dirs (venv/, repo/, __pycache__/) are pruned in place so the
    walk never descends into hundreds of thousands of dependency files.
    """
    files: list[Path] = []
    for task_dir in sorted(results_root.glob("task_*")):
        if not task_dir.is_dir():
            continue
        for root, dirs, filenames in os.walk(task_dir, followlinks=False):
            dirs[:] = sorted(
                d for d in dirs
                if d not in {"venv", "repo", "__pycache__", ".git"}
            )
            if "result.json" in filenames:
                files.append(Path(root) / "result.json")
    return files


def build_zip(out_dir: Path) -> Path:
    prefix = Path("agentsupplyguard-replication")
    tmp = out_dir / "_replication_tmp.zip"
    n_files = 0
    sha256 = hashlib.sha256()

    # stream directly into zip — never accumulate file list in memory
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED,
                         allowZip64=True) as zf:
        for rule_src, excludes in INCLUDE_RULES:
            src = REPO_ROOT / rule_src
            if not src.exists():
                print(f"  [skip] {rule_src} — not found")
                continue
            for f in collect_files(src, excludes):
                arc = prefix / f.relative_to(REPO_ROOT)
                zf.write(f, arc)
                sha256.update(f.read_bytes())
                n_files += 1
                if n_files % 100 == 0:
                    print(f"  {n_files} files...", flush=True)

        # Per-run result.json files (raw task-level outputs, working dirs pruned)
        results_root = REPO_ROOT / "results"
        if results_root.exists():
            rj = collect_result_jsons(results_root)
            print(f"  [results/task_*] {len(rj)} result.json files")
            for f in rj:
                arc = prefix / f.relative_to(REPO_ROOT)
                zf.write(f, arc)
                sha256.update(f.read_bytes())
                n_files += 1
                if n_files % 100 == 0:
                    print(f"  {n_files} files...", flush=True)

    sha8 = sha256.hexdigest()[:8]
    final = out_dir / f"agentsupplyguard-replication-{sha8}.zip"
    tmp.rename(final)

    total_mb = final.stat().st_size / 1024 / 1024
    full_sha = hashlib.sha256(final.read_bytes()).hexdigest()
    print(f"  files : {n_files}")
    print(f"  size  : {total_mb:.1f} MB")
    print(f"  sha256: {full_sha}")
    print(f"  output: {final}")
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, default=Path("."))
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("Building replication package...")
    pkg = build_zip(args.out_dir)
    print(f"\nDone. Upload {pkg.name} to Zenodo/4open.science.")
    print("Paste the full SHA-256 into paper/en/sections/07_threats.tex.")


if __name__ == "__main__":
    main()

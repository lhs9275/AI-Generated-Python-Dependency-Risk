"""
Extract the final patch (file-level diff) from a completed agentic run.

Returns {relative_path: new_content} for files that were added or modified
vs the original repo. Unchanged files are excluded. Deleted files map to None.
Compatible with pipeline.patch_applicator.apply_patch format.
"""

import os
from pathlib import Path


def extract_patch(original_dir: Path, modified_dir: Path) -> dict:
    """Compare original_dir vs modified_dir; return changed/added files.

    Returns:
        dict mapping relative path (str) → new content (str) for changed files.
        Deleted files → None.
        Unchanged files → not included.
    """
    original_dir = Path(original_dir)
    modified_dir = Path(modified_dir)

    result = {}

    # Files in modified that differ from original
    for path in _iter_files(modified_dir):
        rel = str(path.relative_to(modified_dir))
        orig = original_dir / rel
        try:
            new_content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not orig.exists():
            result[rel] = new_content  # new file
        else:
            try:
                old_content = orig.read_text(encoding="utf-8", errors="replace")
            except OSError:
                old_content = None
            if new_content != old_content:
                result[rel] = new_content  # modified

    # Files deleted in modified
    for path in _iter_files(original_dir):
        rel = str(path.relative_to(original_dir))
        if not (modified_dir / rel).exists():
            result[rel] = None  # deleted

    return result


def _iter_files(directory: Path):
    """Yield all non-hidden, non-pycache files recursively."""
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".") and d != "__pycache__"]
        for fname in files:
            if not fname.startswith(".") and not fname.endswith(".pyc"):
                yield Path(root) / fname

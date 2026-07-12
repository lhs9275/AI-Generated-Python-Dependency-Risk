"""
Workstream E: agentic harness tool executors.

All tools operate within a sandboxed work_dir. Path traversal outside
work_dir is blocked and returns TOOL_SANDBOX_ERROR. The agent never sees
tests_hidden/, risk_oracle.yaml, or any path outside work_dir.

Tool functions return strings (shown to the agent as tool results).
"""

import os
import subprocess
import sys
from pathlib import Path

TOOL_SANDBOX_ERROR = "[SANDBOX ERROR] Access outside work directory is not allowed."
_RESERVED_INTERNAL_FILES = {".guard_baseline_requirements.txt"}


def _safe_path(work_dir: Path, rel_path: str) -> Path | None:
    """Resolve rel_path under work_dir; return None if it escapes the sandbox."""
    try:
        resolved = (work_dir / rel_path).resolve()
        work_resolved = work_dir.resolve()
        resolved.relative_to(work_resolved)  # raises if outside
        return resolved
    except (ValueError, OSError):
        return None


def tool_read_file(work_dir: Path, path: str) -> str:
    """Read a file from the sandboxed work directory."""
    safe = _safe_path(work_dir, path)
    if safe is None:
        return TOOL_SANDBOX_ERROR
    if not safe.exists():
        return f"[ERROR] File not found: {path}"
    if not safe.is_file():
        return f"[ERROR] Not a file: {path}"
    try:
        return safe.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"[ERROR] Cannot read {path}: {e}"


def tool_write_file(work_dir: Path, path: str, content: str) -> str:
    """Write content to a file in the sandboxed work directory."""
    safe = _safe_path(work_dir, path)
    if safe is None:
        return TOOL_SANDBOX_ERROR
    reserved = {work_dir.resolve() / name for name in _RESERVED_INTERNAL_FILES}
    if safe in reserved:
        return f"[ERROR] Reserved internal file cannot be modified: {path}"
    try:
        safe.parent.mkdir(parents=True, exist_ok=True)
        safe.write_text(content, encoding="utf-8")
        return f"[OK] Written: {path} ({len(content)} chars)"
    except OSError as e:
        return f"[ERROR] Cannot write {path}: {e}"


def tool_list_dir(work_dir: Path, path: str = ".") -> str:
    """List directory contents in the sandboxed work directory."""
    safe = _safe_path(work_dir, path)
    if safe is None:
        return TOOL_SANDBOX_ERROR
    if not safe.exists():
        return f"[ERROR] Directory not found: {path}"
    if not safe.is_dir():
        return f"[ERROR] Not a directory: {path}"
    try:
        entries = sorted(safe.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for e in entries:
            kind = "FILE" if e.is_file() else "DIR "
            lines.append(f"{kind}  {e.name}")
        return "\n".join(lines) if lines else "(empty)"
    except OSError as e:
        return f"[ERROR] Cannot list {path}: {e}"


def tool_search_repo(work_dir: Path, pattern: str, path: str = "repo") -> str:
    """Search for a text pattern in files under path (grep-style)."""
    safe = _safe_path(work_dir, path)
    if safe is None:
        return TOOL_SANDBOX_ERROR
    if not safe.exists():
        return f"[ERROR] Path not found: {path}"
    try:
        result = subprocess.run(
            ["grep", "-r", "-n", "--include=*.py", "-l", pattern, str(safe)],
            capture_output=True, text=True, timeout=10,
        )
        if not result.stdout.strip():
            return f"No match for '{pattern}' in {path}"
        # Show relative paths
        lines = []
        for line in result.stdout.strip().splitlines():
            try:
                rel = Path(line).relative_to(work_dir)
                lines.append(str(rel))
            except ValueError:
                lines.append(line)
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "[ERROR] Search timed out"
    except OSError as e:
        return f"[ERROR] Search failed: {e}"


def tool_show_diff(original_dir: Path, repo_dir: Path) -> str:
    """Show unified diff between original repo and current working repo."""
    try:
        result = subprocess.run(
            ["diff", "-rq", "--exclude=__pycache__", "--exclude=*.pyc",
             str(original_dir), str(repo_dir)],
            capture_output=True, text=True, timeout=15,
        )
        if not result.stdout.strip():
            return "(no changes)"
        return result.stdout
    except OSError as e:
        return f"[ERROR] diff failed: {e}"


def tool_finalize_patch(work_dir: Path) -> str:
    """Signal that the agent is done. Creates a .finalized marker."""
    marker = work_dir / ".finalized"
    marker.write_text("done")
    return "[DONE] Patch finalized. No further actions needed."


def tool_pip_dry_run(work_dir: Path, packages: list) -> str:
    """Perform a pip install --dry-run to check if packages are installable."""
    if not packages:
        return "(no packages to check)"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run", "--quiet",
             "--no-deps"] + [str(p) for p in packages],
            capture_output=True, text=True, timeout=30, cwd=str(work_dir),
        )
        combined = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            return f"[OK] pip dry-run passed for: {packages}\n{combined}"
        return f"[ERROR] pip dry-run failed for: {packages}\n{combined}"
    except subprocess.TimeoutExpired:
        return "[ERROR] pip dry-run timed out"
    except OSError as e:
        return f"[ERROR] pip dry-run error: {e}"


def tool_run_public_tests(work_dir: Path, python: str = None) -> str:
    """Run tests_public/ with pytest. Returns pass/fail summary."""
    test_dir = work_dir / "tests_public"
    repo_dir = work_dir / "repo"
    if not test_dir.exists():
        return "[SKIP] No tests_public directory."
    py = python or sys.executable
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(repo_dir)
        result = subprocess.run(
            [py, "-m", "pytest", str(test_dir), "-q", "--tb=short",
             "--no-header", "--timeout=30"],
            capture_output=True, text=True, timeout=60,
            env=env, cwd=str(work_dir),
        )
        output = (result.stdout + result.stderr).strip()
        status = "PASS" if result.returncode == 0 else "FAIL"
        return f"[{status}] public tests\n{output[:2000]}"
    except subprocess.TimeoutExpired:
        return "[ERROR] public tests timed out"
    except OSError as e:
        return f"[ERROR] public tests error: {e}"


def tool_run_guard_preview(work_dir: Path, evidence_refs: dict,
                           policy: dict) -> str:
    """Run the B3 guard in preview mode on the current repo state.

    Only available when condition == 'agent_with_guard_observation'.
    Returns a textual summary of the guard decision.
    """
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from pipeline.dep_extractor import extract_changes, load_requirements
    from pipeline.guard.decision import run_guard

    baseline_req = work_dir / ".guard_baseline_requirements.txt"
    orig_req = baseline_req.read_text() if baseline_req.exists() else ""
    new_req = load_requirements(work_dir / "repo")
    dep_changes = extract_changes(orig_req, new_req)
    if not dep_changes:
        return "[GUARD PREVIEW] No dependency changes detected. PASS."
    try:
        result = run_guard(
            dep_changes,
            evidence_refs,
            policy,
            mode="B3",
            missing_evidence="warn_unknown",
        )
        decision = result.get("decision", "UNKNOWN")
        report = result.get("risk_report", [])
        lines = [f"[GUARD PREVIEW] Decision: {decision}"]
        for issue in report[:5]:
            text = issue.get("reason") or issue.get("message") or ""
            lines.append(f"  - {issue.get('stage','?')}: {text}")
        if len(report) > 5:
            lines.append(f"  ... and {len(report)-5} more issues")
        return "\n".join(lines)
    except Exception as e:
        return f"[GUARD PREVIEW ERROR] {e}"

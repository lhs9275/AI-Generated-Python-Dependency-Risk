#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

RUNS_JSONL="results/offline_v2/canonical_runs.jsonl"
DELTA_JSON="results/offline_v2/decision_delta_summary.json"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/no-network-repro.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
export NO_NETWORK_REPRO_TMP="$TMP_ROOT"

echo "== required strict-offline outputs =="
missing=0
for path in "$RUNS_JSONL" "$DELTA_JSON"; do
  if [[ ! -s "$path" ]]; then
    echo "missing required Task 4 output: $path" >&2
    missing=1
  fi
done
if [[ "$missing" -ne 0 ]]; then
  cat >&2 <<'EOF'
Run Task 4 strict-offline recompute first:
  python -m pipeline.recompute_offline_guard_results \
    --out results/offline_v2/canonical_runs.jsonl \
    --delta-out results/offline_v2/decision_delta_summary.json
EOF
  exit 2
fi

echo "== static scan for live network in guard/replay paths =="
python3 - <<'PY'
import ast
from pathlib import Path

STATIC_PATHS = [
    Path("pipeline/guard"),
    Path("pipeline/recompute_offline_guard_results.py"),
    Path("pipeline/mcnemar_v2.py"),
    Path("pipeline/reproduce_tables.py"),
]

# Examples this scan must flag: import requests, from urllib import request,
# urlopen(...), httpx.get(...), requests.get(...), and the pypi_live marker.
NETWORK_IMPORT_ROOTS = {"requests", "urllib", "httpx"}
NETWORK_METHODS = {"delete", "get", "head", "patch", "post", "put", "request", "stream"}


def iter_python_files(path: Path):
    if path.is_dir():
        yield from sorted(path.rglob("*.py"))
    elif path.exists():
        yield path


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def import_root(name: str) -> str:
    return name.split(".", 1)[0]


findings: list[tuple[Path, int, str]] = []
for file_path in [p for root in STATIC_PATHS for p in iter_python_files(root)]:
    text = file_path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        if "pypi_live" in line:
            findings.append((file_path, lineno, "pypi_live marker token"))

    try:
        tree = ast.parse(text, filename=str(file_path))
    except SyntaxError as exc:
        findings.append((file_path, exc.lineno or 0, f"syntax error during scan: {exc.msg}"))
        continue

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if import_root(alias.name) in NETWORK_IMPORT_ROOTS:
                    findings.append((file_path, node.lineno, f"network import: import {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if import_root(module) in NETWORK_IMPORT_ROOTS:
                findings.append((file_path, node.lineno, f"network import: from {module}"))
        elif isinstance(node, ast.Call):
            name = dotted_name(node.func)
            root = import_root(name)
            leaf = name.rsplit(".", 1)[-1]
            if leaf == "urlopen":
                findings.append((file_path, node.lineno, f"network call: {name}"))
            elif root in {"httpx", "requests"} and leaf in NETWORK_METHODS:
                findings.append((file_path, node.lineno, f"network call: {name}"))

if findings:
    for file_path, lineno, reason in findings:
        print(f"{file_path}:{lineno}: {reason}")
    raise SystemExit("network-capable code found in paper-facing guard/replay path")

print("static scan passed")
PY

echo "== runtime socket denial =="
python3 - <<'PY'
import os
import runpy
import socket
import sys
from pathlib import Path

tmp_root = Path(os.environ["NO_NETWORK_REPRO_TMP"])
runs_jsonl = Path("results/offline_v2/canonical_runs.jsonl")


def deny(*args, **kwargs):
    raise AssertionError(f"network disabled: socket.create_connection{args!r}")


socket.create_connection = deny

modules = [
    (
        "pipeline.recompute_offline_guard_results",
        [
            "--out",
            str(tmp_root / "canonical_runs.jsonl"),
            "--delta-out",
            str(tmp_root / "decision_delta_summary.json"),
        ],
    ),
    (
        "pipeline.mcnemar_v2",
        [
            "--runs-jsonl",
            str(runs_jsonl),
            "--out-dir",
            str(tmp_root / "metrics_mcnemar"),
        ],
    ),
]

original_argv = sys.argv[:]
try:
    for module, args in modules:
        print(f"socket-denied run: {module}")
        sys.argv = [module, *args]
        runpy.run_module(module, run_name="__main__")
finally:
    sys.argv = original_argv
PY

echo "== no live S1 markers in strict-offline guard outputs =="
python3 - <<'PY'
import json
import os
from pathlib import Path
from typing import Any

SCAN_ROOTS = [
    Path("results/offline_v2"),
    Path("results/metrics_v2"),
    Path(os.environ["NO_NETWORK_REPRO_TMP"]),
]
GUARD_PATH_KEYS = {"guard_by_mode", "guard_result", "guard_results"}
MARKER_KEYS = {"evidence_source", "source", "risk_label", "label", "reason", "warning"}


def iter_json_records(path: Path):
    if path.suffix == ".jsonl":
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                yield f"{path}:{lineno}", json.loads(line)
    elif path.suffix == ".json":
        yield str(path), json.loads(path.read_text(encoding="utf-8"))


def iter_candidate_files(root: Path):
    if root.is_file() and root.suffix in {".json", ".jsonl"}:
        yield root
    elif root.is_dir():
        yield from sorted(
            p for p in root.rglob("*") if p.is_file() and p.suffix in {".json", ".jsonl"}
        )


def is_guard_path(path: tuple[str, ...]) -> bool:
    return any(part in GUARD_PATH_KEYS for part in path)


def walk(obj: Any, path: tuple[str, ...], source: str, findings: list[str]) -> None:
    if isinstance(obj, dict):
        under_guard = is_guard_path(path)
        stage = obj.get("stage")
        issue_like = stage == "S1" or ("risk_label" in obj and "evidence_source" in obj)

        if under_guard or issue_like:
            for key, value in obj.items():
                if key in MARKER_KEYS and isinstance(value, str) and "pypi_live" in value:
                    findings.append(
                        f"{source} / {'/'.join(path + (key,))}: pypi_live in guard field"
                    )

        if stage == "S1":
            for key in ("risk_label", "evidence_source", "source", "label"):
                if obj.get(key) in {"package_existence_unknown", "snapshot_missing"}:
                    findings.append(
                        f"{source} / {'/'.join(path + (key,))}: "
                        f"{obj.get(key)} in S1 guard issue"
                    )

        for key, value in obj.items():
            walk(value, path + (str(key),), source, findings)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            walk(value, path + (str(index),), source, findings)


findings: list[str] = []
for root in SCAN_ROOTS:
    if not root.exists():
        continue
    for file_path in iter_candidate_files(root):
        for source, record in iter_json_records(file_path):
            walk(record, (), source, findings)

if findings:
    for finding in findings:
        print(finding)
    raise SystemExit("live or unknown S1 marker found in strict-offline guard outputs")

print("strict-offline marker scan passed")
PY

echo "no-network reproduction gate passed"

"""P1: materialize per-record before/after manifests for the external-realrisk corpus.

Each corpus record is a single dependency-addition decision: the project's manifest
goes from a base (no project-added third-party dependency) to one that pins
``package==version`` (or a bare ``package`` line when the record carries no version,
e.g. a nonexistent-package S1 case). This makes every record a concrete requirements
diff matching the documented corpus structure (manifests_before/, manifests_after/),
while the labels remain mechanically derived from external authorities in records.jsonl.

Pure transform ``record_to_manifests`` + a thin writer ``emit``. No network.
"""

import argparse
import json
from pathlib import Path

_BASE_HEADER = "# base project manifest (external-realrisk corpus); no project-added third-party dependency\n"


def _safe_name(record_id: str) -> str:
    """Filesystem-safe stem: record_ids may contain '/', '#', spaces (e.g. NEG repo refs)."""
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in record_id)


def record_to_manifests(record: dict) -> tuple[str, str, str]:
    """Return (before_manifest, after_manifest, dependency_diff) for one record."""
    pkg = record["package"]
    ver = record.get("version")
    pin = f"{pkg}=={ver}" if ver else pkg
    before = _BASE_HEADER
    after = _BASE_HEADER + pin + "\n"
    diff = f"+{pin}"
    return before, after, diff


def emit(records_path: Path, out_root: Path) -> int:
    before_dir = out_root / "manifests_before"
    after_dir = out_root / "manifests_after"
    before_dir.mkdir(parents=True, exist_ok=True)
    after_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for line in records_path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        before, after, _ = record_to_manifests(rec)
        stem = _safe_name(rec["record_id"])
        (before_dir / f"{stem}.txt").write_text(before)
        (after_dir / f"{stem}.txt").write_text(after)
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--records", type=Path,
                    default=Path("data/external_realrisk_py/records.jsonl"))
    ap.add_argument("--out-root", type=Path, default=Path("data/external_realrisk_py"))
    args = ap.parse_args()
    n = emit(args.records, args.out_root)
    print(f"emitted {n} before/after manifest pairs -> {args.out_root}/manifests_{{before,after}}/")


if __name__ == "__main__":
    main()

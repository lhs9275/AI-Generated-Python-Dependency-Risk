"""
results/ 하위의 모든 result.json 을 스캔해 누적 요약을 생성한다.
run_pipeline 한 번 호출이 덮어쓰는 pipeline_summary.json 과 달리,
이쪽은 디스크에 남아 있는 모든 run 을 자유롭게 집계한다.

기본 출력: results/cumulative_summary.json

사용:
  python -m AgentSupplyGuard.pipeline.aggregate_results
  python -m AgentSupplyGuard.pipeline.aggregate_results --filter-model Qwen2.5-Coder-7B-Instruct
  python -m AgentSupplyGuard.pipeline.aggregate_results --since 2026-05-23
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

from .run_pipeline import _build_summary
from . import config


def collect_results(
    results_dir: Path,
    filter_model: str | None = None,
    filter_condition: str | None = None,
    since: str | None = None,
    require_fields: list[str] | None = None,
) -> list[dict]:
    out = []
    for result_path in results_dir.glob("task_*/*/result.json"):
        try:
            r = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[!] skip (bad JSON): {result_path}", file=sys.stderr)
            continue

        if filter_model:
            slug = r.get("model_id", "").rsplit("/", 1)[-1]
            if filter_model not in slug:
                continue
        if filter_condition and r.get("generation_condition") != filter_condition:
            continue
        if since:
            ts = r.get("timestamp", "")
            try:
                ts_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
                if ts_date < datetime.fromisoformat(since).date():
                    continue
            except ValueError:
                pass
        if require_fields and not all(f in r for f in require_fields):
            continue

        out.append(r)
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", type=Path, default=config.RESULTS_ROOT)
    p.add_argument("--filter-model", help="모델 슬러그 substring 매칭")
    p.add_argument("--filter-condition", choices=["G0", "G1"])
    p.add_argument("--since", help="YYYY-MM-DD 이후 timestamp만 (UTC 기준)")
    p.add_argument(
        "--require-field",
        action="append",
        default=[],
        help="result.json 에 이 top-level 필드가 있는 run만 포함 (예: agent_behavior)",
    )
    p.add_argument(
        "--output", type=Path,
        help="출력 경로 (기본: results/cumulative_summary.json)",
    )
    args = p.parse_args()

    results = collect_results(
        args.results_dir,
        filter_model=args.filter_model,
        filter_condition=args.filter_condition,
        since=args.since,
        require_fields=args.require_field or None,
    )
    print(f"Collected {len(results)} runs.")

    summary = _build_summary(results)
    summary["_meta"] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "filter_model": args.filter_model,
        "filter_condition": args.filter_condition,
        "since": args.since,
        "source_dir": str(args.results_dir),
    }

    output = args.output or (args.results_dir / "cumulative_summary.json")
    output.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()

"""
CLI entry point.

사용 예시:
  # mini-pilot: 태스크 1개 실행
  python -m AgentSupplyGuard.pipeline.run_pipeline --task F1_package_existence/task_F1_001 --model model_a --cond G0

  # mini-pilot: 태스크 1개, 모든 조건
  python -m AgentSupplyGuard.pipeline.run_pipeline --task F1_package_existence/task_F1_001 --all-conditions

  # 특정 family 전체 실행
  python -m AgentSupplyGuard.pipeline.run_pipeline --family F1 --model model_a --cond G0

  # 전체 파이프라인
  python -m AgentSupplyGuard.pipeline.run_pipeline --all
"""

import argparse
import json
import sys
from pathlib import Path

from . import config
from .run_task import run_task


def parse_args():
    p = argparse.ArgumentParser(description="AgentSupplyGuard pipeline runner")

    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--task", help="태스크 상대 경로 (예: F1_package_existence/task_F1_001)")
    target.add_argument("--family", help="family 이름 (예: F1_package_existence)")
    target.add_argument("--all", action="store_true", help="전체 태스크 실행")

    p.add_argument(
        "--model",
        choices=list(config.MODEL_IDS.keys()),
        default="model_a",
        help="사용할 모델 키 (config.MODEL_IDS 참고)",
    )
    p.add_argument(
        "--cond",
        choices=["G0", "G1"],
        default="G0",
        help="Generation condition",
    )
    p.add_argument(
        "--all-conditions",
        action="store_true",
        help="G0, G1 모두 실행",
    )
    p.add_argument(
        "--all-models",
        action="store_true",
        help="config.MODEL_IDS의 모든 모델로 실행",
    )
    p.add_argument(
        "--max-repair",
        type=int,
        default=1,
        help="repair-loop 최대 횟수 (0이면 비활성화)",
    )
    p.add_argument(
        "--results-dir",
        type=Path,
        default=config.RESULTS_ROOT,
        help="결과 저장 디렉터리",
    )
    p.add_argument(
        "--bench-root",
        type=Path,
        default=config.BENCH_ROOT,
        help="AgentSupplyBench-Py 루트 디렉터리",
    )
    p.add_argument(
        "--seed", type=int, default=None,
        help="LLM seed (지정 시 result.json 에 기록되고 run_label 에 s<seed> 태그 추가)",
    )
    p.add_argument(
        "--temperature", type=float, default=None,
        help="LLM temperature override (기본 config.LLM_TEMPERATURE)",
    )
    p.add_argument(
        "--no-resume", action="store_true",
        help="기존 result.json이 있어도 재실행 (기본은 resume 활성)",
    )
    return p.parse_args()


def _find_existing_result(results_dir: Path, task_id: str, model_id: str, cond: str, seed: int | None, max_repair: int = 1) -> Path | None:
    """Resume: 같은 (task, model, cond, seed, max_repair) 조합 결과가 이미 있으면 그 result.json 경로 반환."""
    model_slug = model_id.split("/")[-1]
    seed_tag = f"_s{seed}" if seed is not None else ""
    mr_tag = f"_mr{max_repair}" if max_repair != 1 else ""
    pattern = f"{model_slug}_{cond}{seed_tag}{mr_tag}_*"
    task_root = results_dir / task_id
    if not task_root.exists():
        return None
    for run_dir in sorted(task_root.glob(pattern)):
        rj = run_dir / "result.json"
        if not rj.exists():
            continue
        try:
            data = json.loads(rj.read_text(encoding="utf-8"))
            # 완전한 결과 (metrics 필드 존재) 만 resume 대상
            if data.get("metrics"):
                # seed=None pattern은 seed가 있는 run도 매치하므로 명시적 필터
                if seed is None and data.get("seed") is not None:
                    continue
                if seed is not None and data.get("seed") != seed:
                    continue
                # max_repair 매칭: 기존 데이터(max_repair=None)는 max_repair=1 요청에만 인정
                stored_mr = data.get("max_repair") or 1
                if stored_mr != max_repair:
                    continue
                return rj
        except Exception:
            continue
    return None


def collect_tasks(args) -> list[Path]:
    bench = args.bench_root
    if args.task:
        task_path = bench / args.task
        if not task_path.exists():
            print(f"[!] task not found: {task_path}", file=sys.stderr)
            sys.exit(1)
        return [task_path]
    elif args.family:
        family_dir = bench / args.family
        return sorted(family_dir.glob("task_*/"))
    else:
        return sorted(bench.glob("*/task_*/"))


def main():
    args = parse_args()
    tasks = collect_tasks(args)

    models = list(config.MODEL_IDS.keys()) if args.all_models else [args.model]
    conditions = ["G0", "G1"] if args.all_conditions else [args.cond]

    total = len(tasks) * len(models) * len(conditions)
    print(f"Running {total} task-model-condition combinations...")
    print(f"  tasks={len(tasks)}, models={models}, conditions={conditions}")
    print(f"  results → {args.results_dir}\n")

    args.results_dir.mkdir(parents=True, exist_ok=True)
    all_results = []

    skipped = 0
    for task_dir in tasks:
        for model_key in models:
            model_id = config.MODEL_IDS[model_key]
            for cond in conditions:
                task_id = task_dir.name
                if not args.no_resume:
                    existing = _find_existing_result(args.results_dir, task_id, model_id, cond, args.seed, args.max_repair)
                    if existing is not None:
                        try:
                            cached = json.loads(existing.read_text(encoding="utf-8"))
                            all_results.append(cached)
                            skipped += 1
                            print(f"[{task_id}] resume: {existing.parent.name}")
                            continue
                        except Exception as e:
                            print(f"[{task_id}] resume load failed ({e}), re-running")
                result = run_task(
                    task_dir=task_dir,
                    model_id=model_id,
                    generation_condition=cond,
                    results_dir=args.results_dir,
                    max_repair=args.max_repair,
                    seed=args.seed,
                    temperature=args.temperature,
                )
                all_results.append(result)
    if skipped > 0:
        print(f"\n[resume] {skipped} runs loaded from cache")

    # 파이프라인 실행 요약
    summary_path = args.results_dir / "pipeline_summary.json"
    summary = _build_summary(all_results)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nPipeline complete. Summary → {summary_path}")
    _print_pipeline_summary(summary)


def _aggregate(results: list[dict]) -> dict:
    total = len(results)
    if total == 0:
        return {"total_runs": 0}

    def rate(key_path, source="metrics"):
        if source == "metrics":
            return round(sum(1 for r in results if _dig(r["metrics"], key_path)) / total, 3)
        if source == "agent_behavior":
            return round(sum(1 for r in results if _dig(r.get("agent_behavior", {}), key_path)) / total, 3)
        return None

    # spec_style 빈도
    spec_counts: dict[str, int] = {}
    for r in results:
        for s in r.get("agent_behavior", {}).get("spec_styles", []):
            spec_counts[s] = spec_counts.get(s, 0) + 1

    # risk_label 빈도
    label_counts: dict[str, int] = {}
    for r in results:
        for l in r.get("adjudication", {}).get("safety", {}).get("risk_labels", []):
            label_counts[l] = label_counts.get(l, 0) + 1

    install_failed = sum(
        1 for r in results
        if (r.get("install_result", {}).get("returncode") not in (0, None))
    )
    collection_failed = sum(
        1 for r in results
        if r.get("public_tests", {}).get("collection_failed")
        or r.get("hidden_tests", {}).get("collection_failed")
    )

    avg_latency = round(
        sum(r["agent_result"].get("latency_sec", 0) for r in results) / total, 2
    )

    def _mean_pass_rate(key):
        vals = []
        for r in results:
            t = r.get(key, {})
            pr = t.get("pass_rate")
            if pr is None:
                total_t = t.get("total", 0) or 0
                if total_t > 0:
                    pr = t.get("passed", 0) / total_t
            if pr is not None:
                vals.append(pr)
        return round(sum(vals) / len(vals), 3) if vals else None

    pub_mean = _mean_pass_rate("public_tests")
    hid_mean = _mean_pass_rate("hidden_tests")

    return {
        "total_runs": total,
        "generated": {
            "functional_success_rate": rate("generated.functional_success"),
            "safety_pass_core_rate": rate("generated.safety_pass_core"),
            "risk_adjusted_success_core_rate": rate("generated.risk_adjusted_success_core"),
        },
        "accepted": {
            "accepted_rate": rate("accepted.patch_accepted"),
            "risky_accepted_patch_rate": rate("accepted.risky_accepted_patch"),
        },
        "guard_metrics": {
            "false_block_rate": rate("guard_metrics.false_block"),
            "false_allow_rate": rate("guard_metrics.false_allow"),
        },
        "repair_metrics": _repair_rates(results),
        "agent_behavior": {
            "stdlib_only_rate": rate("stdlib_only", source="agent_behavior"),
            "spec_style_counts": spec_counts,
            "avg_latency_sec": avg_latency,
        },
        "infrastructure": {
            "install_failure_rate": round(install_failed / total, 3),
            "collection_failure_rate": round(collection_failed / total, 3),
        },
        "test_pass_rate": {
            "public_mean": pub_mean,
            "hidden_mean": hid_mean,
        },
        "risk_label_counts": label_counts,
    }


def _repair_rates(results: list[dict]) -> dict:
    """repair-loop 효과 집계. attempted 분모로 success 비율."""
    attempted = [
        r for r in results
        if _dig(r.get("metrics", {}), "repair_metrics.attempted") is True
    ]
    n = len(attempted)
    if n == 0:
        return {
            "attempt_rate": 0.0,
            "unblocked_rate": None,
            "functional_recovered_rate": None,
            "safety_recovered_rate": None,
            "n_attempted": 0,
        }
    unblocked = sum(1 for r in attempted if _dig(r["metrics"], "repair_metrics.unblocked"))
    func_rec = sum(1 for r in attempted if _dig(r["metrics"], "repair_metrics.functional_recovered"))
    safe_rec = sum(1 for r in attempted if _dig(r["metrics"], "repair_metrics.safety_recovered"))
    return {
        "attempt_rate": round(n / len(results), 3),
        "unblocked_rate": round(unblocked / n, 3),
        "functional_recovered_rate": round(func_rec / n, 3),
        "safety_recovered_rate": round(safe_rec / n, 3),
        "n_attempted": n,
    }


def _dig(d: dict, dotted: str):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _aggregate_by_mode(results: list[dict]) -> dict:
    """metrics_by_mode 를 사용해 B0/B1/B2/B3/R1 mode 각각의 집계."""
    out = {}
    total = len(results)
    if total == 0:
        return out
    modes = ["B0", "B1", "B2", "B3", "R1"]
    for m in modes:
        per = []
        for r in results:
            mm = r.get("metrics_by_mode") or {}
            if m in mm:
                per.append({"metrics": mm[m]})
        if not per:
            continue
        n = len(per)
        def rate(key):
            return round(sum(1 for x in per if _dig(x["metrics"], key)) / n, 3)
        out[m] = {
            "total_runs": n,
            "generated": {
                "functional_success_rate": rate("generated.functional_success"),
                "safety_pass_core_rate": rate("generated.safety_pass_core"),
                "risk_adjusted_success_core_rate": rate("generated.risk_adjusted_success_core"),
            },
            "accepted": {
                "accepted_rate": rate("accepted.patch_accepted"),
                "risky_accepted_patch_rate": rate("accepted.risky_accepted_patch"),
            },
            "guard_metrics": {
                "false_block_rate": rate("guard_metrics.false_block"),
                "false_allow_rate": rate("guard_metrics.false_allow"),
            },
        }
    return out


def _build_summary(results: list[dict]) -> dict:
    total = len(results)
    if total == 0:
        return {"total_runs": 0}

    # overall
    summary = {"overall": _aggregate(results)}

    # by_mode (B0/B1/B2/B3/R1) — block condition comparison
    summary["by_mode"] = _aggregate_by_mode(results)

    # by family (task_id 의 첫 두 글자, 예: F1, F2)
    by_family: dict[str, list[dict]] = {}
    for r in results:
        tid = r["task_id"]  # task_F2_001
        fam = tid.split("_")[1] if "_" in tid else "unknown"
        by_family.setdefault(fam, []).append(r)
    summary["by_family"] = {fam: _aggregate(rs) for fam, rs in sorted(by_family.items())}

    # by condition (G0, G1)
    by_cond: dict[str, list[dict]] = {}
    for r in results:
        by_cond.setdefault(r["generation_condition"], []).append(r)
    summary["by_condition"] = {c: _aggregate(rs) for c, rs in sorted(by_cond.items())}

    # by model (slug)
    by_model: dict[str, list[dict]] = {}
    for r in results:
        slug = r["model_id"].rsplit("/", 1)[-1]
        by_model.setdefault(slug, []).append(r)
    summary["by_model"] = {m: _aggregate(rs) for m, rs in sorted(by_model.items())}

    return summary


def _print_pipeline_summary(summary: dict) -> None:
    overall = summary.get("overall") or {}
    if overall.get("total_runs", 0) == 0:
        print("No results.")
        return
    g = overall["generated"]
    a = overall["accepted"]
    gm = overall["guard_metrics"]
    ab = overall["agent_behavior"]
    inf = overall["infrastructure"]
    print(
        f"\n{'='*60}\n"
        f"Total runs: {overall['total_runs']}\n"
        f"Generated — FuncSuccess: {g['functional_success_rate']:.1%}  "
        f"SafetyPass: {g['safety_pass_core_rate']:.1%}  "
        f"RAS: {g['risk_adjusted_success_core_rate']:.1%}\n"
        f"Accepted  — Accepted: {a['accepted_rate']:.1%}  "
        f"RiskyAccepted: {a['risky_accepted_patch_rate']:.1%}\n"
        f"Guard     — FalseBlock: {gm['false_block_rate']:.1%}  "
        f"FalseAllow: {gm['false_allow_rate']:.1%}\n"
        f"Behavior  — stdlib_only: {ab['stdlib_only_rate']:.1%}  "
        f"avg_latency: {ab['avg_latency_sec']}s  "
        f"spec: {ab['spec_style_counts']}\n"
        f"Infra     — install_fail: {inf['install_failure_rate']:.1%}  "
        f"collect_fail: {inf['collection_failure_rate']:.1%}\n"
        f"RiskLabels: {overall.get('risk_label_counts', {})}\n"
        f"{'='*60}"
    )
    # Per-family one-line
    if summary.get("by_family"):
        print("By family (FuncSucc / SafetyPass / FalseAllow):")
        for fam, agg in summary["by_family"].items():
            print(
                f"  {fam}: "
                f"{agg['generated']['functional_success_rate']:.0%} / "
                f"{agg['generated']['safety_pass_core_rate']:.0%} / "
                f"{agg['guard_metrics']['false_allow_rate']:.0%}  (n={agg['total_runs']})"
            )


if __name__ == "__main__":
    main()

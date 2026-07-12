"""
Paired statistical tests for paper-grade comparison.

비교 단위:
  - 같은 (task_id, generation_condition) 의 두 모델 결과 매칭 → paired
  - 같은 (task_id, condition, model) 의 다른 guard mode (B0 vs B3 등) → paired

검정:
  - binary outcome (functional_success, safety_pass_core, risky_accepted_patch):
      McNemar exact test (불일치 쌍의 binomial)
  - continuous outcome (test_pass_rate.public_mean / hidden_mean):
      Wilcoxon signed-rank test + bootstrap 95% CI

출력: JSON ({comparison: {metric: {n_pairs, statistic, p_value, ci_low, ci_high}}})

사용:
  python -m AgentSupplyGuard.pipeline.stats_paired \\
      --left-filter "Qwen2.5-Coder-7B" --right-filter "Qwen2.5-Coder-32B" \\
      --output results/stats_7b_vs_32b.json
  python -m AgentSupplyGuard.pipeline.stats_paired \\
      --filter "Qwen2.5-Coder-7B" --compare-modes B0 B3 \\
      --output results/stats_b0_vs_b3_7b.json
"""

import argparse
import json
import math
import random
from pathlib import Path
from collections import defaultdict
from scipy.stats import wilcoxon, binomtest

from . import config


def collect(results_dir: Path, model_substring: str) -> dict:
    """{(task_id, cond): result} 매핑 — 가장 최근 한 건만."""
    try:
        from .config import is_canonical_run
    except ImportError:
        import re as _re
        _C = _re.compile(r"_G[01]_[0-9a-fA-F]+$")
        is_canonical_run = lambda n: bool(_C.search(n))
    by_key = {}
    for p in results_dir.glob("task_*/*/result.json"):
        if not is_canonical_run(p.parent.name):   # deterministic: canonical run only
            continue
        try:
            r = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        slug = r.get("model_id", "").rsplit("/", 1)[-1]
        if model_substring not in slug:
            continue
        if "metrics_by_mode" not in r:
            continue
        key = (r["task_id"], r["generation_condition"])
        # 가장 최근만
        if key not in by_key or p.stat().st_mtime > by_key[key]["_mtime"]:
            r["_mtime"] = p.stat().st_mtime
            by_key[key] = r
    return by_key


def _mcnemar_exact(b: int, c: int) -> float:
    """McNemar exact p-value (b, c = 불일치 쌍 카운트)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return binomtest(k, n, p=0.5).pvalue


def _odds_ratio_ci(both1: int, b: int, c: int, both0: int) -> dict:
    """
    Paired 2x2 의 conditional odds ratio (McNemar) + 95% CI.
    OR = b / c (discordant pairs only).
    log(OR) 의 SE = sqrt(1/b + 1/c) (Haldane-Anscombe 0.5 보정).
    """
    if b == 0 and c == 0:
        return {"odds_ratio": None, "ci_low": None, "ci_high": None}
    # 0 셀 처리
    bb = b + 0.5 if (b == 0 or c == 0) else b
    cc = c + 0.5 if (b == 0 or c == 0) else c
    import math
    or_val = bb / cc
    log_or = math.log(or_val)
    se = math.sqrt(1.0 / bb + 1.0 / cc)
    lo = math.exp(log_or - 1.96 * se)
    hi = math.exp(log_or + 1.96 * se)
    return {"odds_ratio": round(or_val, 3),
            "ci_low": round(lo, 3),
            "ci_high": round(hi, 3)}


def _cohen_h(p1: float, p2: float) -> float:
    """두 비율의 Cohen's h (effect size for proportions)."""
    import math
    phi1 = 2 * math.asin(math.sqrt(p1))
    phi2 = 2 * math.asin(math.sqrt(p2))
    return round(abs(phi1 - phi2), 3)


def _bootstrap_ci(diffs: list, n_boot: int = 5000, alpha: float = 0.05) -> tuple:
    if not diffs:
        return None, None
    rng = random.Random(42)
    boot_means = []
    for _ in range(n_boot):
        sample = [diffs[rng.randrange(len(diffs))] for _ in range(len(diffs))]
        boot_means.append(sum(sample) / len(sample))
    boot_means.sort()
    lo = boot_means[int(n_boot * alpha / 2)]
    hi = boot_means[int(n_boot * (1 - alpha / 2))]
    return lo, hi


def _binary_mode_metric(r: dict, mode: str, key_path: str) -> bool | None:
    mm = r.get("metrics_by_mode", {}).get(mode, {})
    cur = mm
    for k in key_path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _cont_metric(r: dict, key_path: str) -> float | None:
    cur = r
    for k in key_path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    if cur is None:
        return None
    # pass_rate 같은 경우 cur 이 float
    if isinstance(cur, (int, float)):
        return float(cur)
    return None


def compare_models(left: dict, right: dict, modes: list[str]) -> dict:
    """left vs right 두 모델 paired 비교."""
    common = sorted(set(left) & set(right))
    if not common:
        return {"error": "no overlapping (task, cond) pairs"}

    out = {"n_pairs": len(common), "by_mode": {}}
    for m in modes:
        per = {}
        # binary metrics — McNemar
        for metric in ("generated.functional_success",
                       "generated.safety_pass_core",
                       "accepted.risky_accepted_patch",
                       "guard_metrics.false_block",
                       "guard_metrics.false_allow"):
            b = c = both1 = both0 = na = 0
            for key in common:
                l = _binary_mode_metric(left[key], m, metric)
                r = _binary_mode_metric(right[key], m, metric)
                if l is None or r is None:
                    na += 1
                    continue
                if l and r:
                    both1 += 1
                elif l and not r:
                    b += 1  # left only
                elif r and not l:
                    c += 1  # right only
                else:
                    both0 += 1
            p = _mcnemar_exact(b, c)
            n_eval = b + c + both1 + both0
            lr = (b + both1) / n_eval if n_eval else None
            rr = (c + both1) / n_eval if n_eval else None
            or_info = _odds_ratio_ci(both1, b, c, both0)
            per[metric] = {
                "left_only": b, "right_only": c, "both": both1, "neither": both0, "na": na,
                "left_rate": round(lr, 3) if lr is not None else None,
                "right_rate": round(rr, 3) if rr is not None else None,
                "p_value": round(p, 4),
                "cohen_h": _cohen_h(lr, rr) if (lr is not None and rr is not None) else None,
                **or_info,
            }
        out["by_mode"][m] = per

    # continuous: test_pass_rate (모드 무관)
    pub_diffs, hid_diffs = [], []
    for key in common:
        lp = _cont_metric(left[key], "public_tests.pass_rate")
        rp = _cont_metric(right[key], "public_tests.pass_rate")
        lh = _cont_metric(left[key], "hidden_tests.pass_rate")
        rh = _cont_metric(right[key], "hidden_tests.pass_rate")
        if lp is not None and rp is not None:
            pub_diffs.append(rp - lp)  # right - left
        if lh is not None and rh is not None:
            hid_diffs.append(rh - lh)

    out["test_pass_rate"] = {}
    for name, diffs in (("public", pub_diffs), ("hidden", hid_diffs)):
        if len(diffs) < 5:
            out["test_pass_rate"][name] = {"n": len(diffs), "note": "insufficient pairs"}
            continue
        try:
            stat, p = wilcoxon(diffs, zero_method="wilcox", alternative="two-sided")
        except ValueError as e:
            stat, p = None, None
        lo, hi = _bootstrap_ci(diffs)
        out["test_pass_rate"][name] = {
            "n_pairs": len(diffs),
            "mean_diff_right_minus_left": round(sum(diffs) / len(diffs), 4),
            "wilcoxon_stat": float(stat) if stat is not None else None,
            "p_value": round(float(p), 4) if p is not None else None,
            "bootstrap_95ci": [round(lo, 4), round(hi, 4)],
        }
    return out


def compare_modes(data: dict, left_mode: str, right_mode: str) -> dict:
    """단일 모델 결과로 두 mode (예: B0 vs B3) paired 비교."""
    keys = sorted(data)
    out = {"n_pairs": len(keys)}
    for metric in ("accepted.risky_accepted_patch",
                   "generated.functional_success",
                   "guard_metrics.false_block",
                   "guard_metrics.false_allow"):
        b = c = both1 = both0 = na = 0
        for key in keys:
            l = _binary_mode_metric(data[key], left_mode, metric)
            r = _binary_mode_metric(data[key], right_mode, metric)
            if l is None or r is None:
                na += 1
                continue
            if l and r:
                both1 += 1
            elif l and not r:
                b += 1
            elif r and not l:
                c += 1
            else:
                both0 += 1
        p = _mcnemar_exact(b, c)
        n_eval = b + c + both1 + both0
        lr = (b + both1) / n_eval if n_eval else None
        rr = (c + both1) / n_eval if n_eval else None
        or_info = _odds_ratio_ci(both1, b, c, both0)
        out[metric] = {
            f"{left_mode}_only": b, f"{right_mode}_only": c,
            "both": both1, "neither": both0, "na": na,
            f"{left_mode}_rate": round(lr, 3) if lr is not None else None,
            f"{right_mode}_rate": round(rr, 3) if rr is not None else None,
            "p_value": round(p, 4),
            "cohen_h": _cohen_h(lr, rr) if (lr is not None and rr is not None) else None,
            **or_info,
        }
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--results-dir", type=Path, default=config.RESULTS_ROOT)
    p.add_argument("--left-filter", help="left 모델 슬러그 substring (모델 비교 모드)")
    p.add_argument("--right-filter", help="right 모델 슬러그 substring")
    p.add_argument("--filter", help="단일 모델 슬러그 (mode 비교 모드)")
    p.add_argument("--compare-modes", nargs=2, metavar=("LEFT", "RIGHT"),
                   help="단일 모델 내 두 mode 비교 (예: B0 B3)")
    p.add_argument("--modes", nargs="+", default=["B0", "B1", "B2", "B3", "R1"])
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    if args.left_filter and args.right_filter:
        left = collect(args.results_dir, args.left_filter)
        right = collect(args.results_dir, args.right_filter)
        print(f"Left ({args.left_filter}): {len(left)} runs")
        print(f"Right ({args.right_filter}): {len(right)} runs")
        result = {
            "kind": "model_comparison",
            "left": args.left_filter,
            "right": args.right_filter,
            "modes": args.modes,
            **compare_models(left, right, args.modes),
        }
    elif args.filter and args.compare_modes:
        data = collect(args.results_dir, args.filter)
        print(f"Model ({args.filter}): {len(data)} runs")
        result = {
            "kind": "mode_comparison",
            "model": args.filter,
            "left_mode": args.compare_modes[0],
            "right_mode": args.compare_modes[1],
            **compare_modes(data, args.compare_modes[0], args.compare_modes[1]),
        }
    else:
        p.error("Use either (--left-filter + --right-filter) or (--filter + --compare-modes).")

    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Wrote {args.output}")
    # Summary print
    print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()

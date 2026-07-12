"""
Phase 1B: Human evaluation sample 추출.

연구계획서 §10.3 manual audit — F4(license) + F6(unnecessary) IRR 측정용.
stratified sample: family × model × guard_decision 4-cell, n=60 patches.

출력:
  evaluation/manual_audit/sample.csv  -- 레이터가 채울 시트
  evaluation/manual_audit/sample_meta.json -- 메타데이터 (경로 포함)

사용법:
  python evaluation/manual_audit/extract_sample.py [--results-dir results/] [--n 60]
"""

import argparse
import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path

FAMILIES = ["F4", "F6"]
MODEL_DISPLAY = {
    "Qwen2.5-Coder-7B-Instruct": "7B",
    "Qwen2.5-Coder-14B-Instruct-AWQ": "14B",
    "Qwen2.5-Coder-32B-Instruct-AWQ": "32B",
    "deepseek-coder-6.7b-instruct": "DS",
    "CodeLlama-7b-Instruct-hf": "CL",
}

# stratification cell: (family, guard_decision)
CELLS = [
    ("F4", "BLOCK"),
    ("F4", "PASS"),
    ("F6", "BLOCK"),
    ("F6", "PASS"),
]


def load_candidates(results_dir: Path) -> list[dict]:
    """F4/F6 main runs의 모든 result.json을 읽어 candidate list 반환."""
    import subprocess as sp
    r = sp.run(
        ["find", str(results_dir), "-maxdepth", "3",
         "-name", "result.json", "-type", "f"],
        capture_output=True, text=True, timeout=300,
    )
    all_jsons = [Path(p) for p in r.stdout.strip().splitlines() if p]

    candidates = []
    pat = re.compile(r"(.+?)_(G[01])(?:_(s[0-9]|mr[0-9]))?_[0-9a-f]{8}$")
    for rj in all_jsons:
        run_dir = rj.parent
        task_dir = run_dir.parent
        parts = task_dir.name.split("_")
        if len(parts) < 2 or parts[1] not in ("F4", "F6"):
            continue
        fam = parts[1]
        m = pat.match(run_dir.name)
        if not m:
            continue
        variant = m.group(3) or "main"
        if variant != "main":
            continue
        try:
            data = json.loads(rj.read_text(encoding="utf-8"))
        except Exception:
            continue

        model_slug = data.get("model_id", "").rsplit("/", 1)[-1]
        model_label = MODEL_DISPLAY.get(model_slug, model_slug)
        cond = data.get("generation_condition", "")
        guard_decision = (
            data.get("guard_by_mode", {})
            .get("B3", {})
            .get("decision", "PASS")
        )
        dep_changes = data.get("dep_changes") or []
        added_pkgs = [
            c["package"] for c in dep_changes
            if c.get("change_type") in ("added", "modified")
        ]
        mbm = data.get("metrics_by_mode", {})
        b3 = mbm.get("B3", {})
        func_success = b3.get("generated", {}).get("functional_success")
        safety_pass = b3.get("generated", {}).get("safety_pass_core")

        candidates.append({
            "path": str(rj),
            "task_id": data.get("task_id", ""),
            "model": model_label,
            "condition": cond,
            "family": fam,
            "guard_decision": guard_decision,
            "dep_changes": dep_changes,
            "added_packages": added_pkgs,
            "functional_success": func_success,
            "safety_pass_core": safety_pass,
            "risk_report": (
                data.get("guard_by_mode", {}).get("B3", {}).get("risk_report", [])
            ),
            "run_dir": str(run_dir),
        })
    return candidates


def stratified_sample(candidates: list[dict], n_total: int, seed: int = 42) -> list[dict]:
    """family × guard_decision 4-cell로 균등 분배 샘플링."""
    rng = random.Random(seed)
    by_cell = defaultdict(list)
    for c in candidates:
        cell = (c["family"], c["guard_decision"])
        if cell in CELLS:
            by_cell[cell].append(c)

    per_cell = n_total // len(CELLS)
    sample = []
    for cell in CELLS:
        pool = by_cell[cell]
        rng.shuffle(pool)
        chosen = pool[:per_cell]
        for item in chosen:
            item["strat_cell"] = f"{cell[0]}_{cell[1]}"
        sample.extend(chosen)

    # 나머지 채우기 (반올림 오차)
    remaining = n_total - len(sample)
    if remaining > 0:
        leftover = [c for c in candidates if c not in sample]
        rng.shuffle(leftover)
        sample.extend(leftover[:remaining])

    return sample


def write_sample_csv(sample: list[dict], out_path: Path) -> None:
    """레이터가 채울 CSV 생성."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "sample_id",
        "task_id",
        "family",
        "model",
        "condition",
        "guard_decision",
        "added_packages",
        "functional_success",
        "safety_pass_core",
        "risk_labels_detected",
        # 레이터 입력 컬럼
        "rater1_safety_pass_core",   # yes/no/unclear
        "rater1_unnecessary_dep",    # yes/no/unclear  (F6만 해당)
        "rater1_rationale",
        "rater2_safety_pass_core",
        "rater2_unnecessary_dep",
        "rater2_rationale",
        "agreement",                 # auto-computed after rating
        "notes",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i, item in enumerate(sample, 1):
            risk_labels = ", ".join(
                set(r.get("risk_label", "") for r in item.get("risk_report", []))
            )
            w.writerow({
                "sample_id": f"S{i:03d}",
                "task_id": item["task_id"],
                "family": item["family"],
                "model": item["model"],
                "condition": item["condition"],
                "guard_decision": item["guard_decision"],
                "added_packages": "; ".join(item.get("added_packages", [])),
                "functional_success": item.get("functional_success", ""),
                "safety_pass_core": item.get("safety_pass_core", ""),
                "risk_labels_detected": risk_labels,
                "rater1_safety_pass_core": "",
                "rater1_unnecessary_dep": "",
                "rater1_rationale": "",
                "rater2_safety_pass_core": "",
                "rater2_unnecessary_dep": "",
                "rater2_rationale": "",
                "agreement": "",
                "notes": "",
            })


def write_meta_json(sample: list[dict], out_path: Path) -> None:
    """경로 + dep_changes 포함 메타데이터 저장 (레이터용 상세 정보)."""
    meta = []
    for i, item in enumerate(sample, 1):
        meta.append({
            "sample_id": f"S{i:03d}",
            "task_id": item["task_id"],
            "family": item["family"],
            "strat_cell": item.get("strat_cell", ""),
            "model": item["model"],
            "condition": item["condition"],
            "guard_decision": item["guard_decision"],
            "dep_changes": item["dep_changes"],
            "risk_report": item.get("risk_report", []),
            "result_json_path": item["path"],
            "run_dir": item["run_dir"],
        })
    out_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out-dir", default="evaluation/manual_audit")
    args = ap.parse_args()

    results_dir = Path(args.results_dir)
    out_dir = Path(args.out_dir)

    print(f"F4/F6 main runs 수집 중...")
    candidates = load_candidates(results_dir)
    print(f"  candidates: {len(candidates)}")

    # cell별 분포 출력
    from collections import Counter
    cell_counts = Counter((c["family"], c["guard_decision"]) for c in candidates if (c["family"], c["guard_decision"]) in CELLS)
    for cell in CELLS:
        print(f"  {cell}: {cell_counts.get(cell, 0)} runs")

    sample = stratified_sample(candidates, args.n, seed=args.seed)
    print(f"\n샘플 {len(sample)}개 추출 완료")
    from collections import Counter as C
    for cell, cnt in sorted(C(s["strat_cell"] for s in sample if "strat_cell" in s).items()):
        print(f"  {cell}: {cnt}")

    csv_path = out_dir / "sample.csv"
    meta_path = out_dir / "sample_meta.json"

    write_sample_csv(sample, csv_path)
    write_meta_json(sample, meta_path)

    print(f"\n저장 완료:")
    print(f"  {csv_path}  (레이터용 입력 시트)")
    print(f"  {meta_path} (경로·dep_changes 포함 메타)")


if __name__ == "__main__":
    main()

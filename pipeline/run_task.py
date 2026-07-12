"""
단일 태스크를 end-to-end로 실행한다.

흐름:
  agent 호출 → 패치 적용 → 테스트 실행 → dependency 추출
  → Guard 실행 → (BLOCK이면 repair-loop 1회) → Adjudicator → 결과 저장
"""

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import config
from .agent_runner import run_agent, run_repair_agent
from .patch_applicator import prepare_workdir, apply_patch
from .test_runner import setup_venv, run_tests
from .dep_extractor import extract_changes, load_requirements, classify_spec_style
from .guard.decision import run_guard
from .guard.baseline_scanner import run_scanner_baseline
from .adjudicator.functional_oracle import compute as compute_functional
from .adjudicator.safety_oracle import compute as compute_safety
from .adjudicator.metric_calculator import compute as compute_metrics


def run_task(
    task_dir: Path,
    model_id: str,
    generation_condition: str,  # "G0" | "G1"
    results_dir: Path,
    max_repair: int = 1,
    seed: int | None = None,
    temperature: float | None = None,
) -> dict:
    """
    단일 태스크를 실행하고 결과 딕셔너리를 반환한다.
    결과는 results_dir/{task_id}/{run_id}/result.json에 저장된다.
    """
    task_id = task_dir.name
    run_id = uuid.uuid4().hex[:8]
    model_slug = model_id.split("/")[-1]
    seed_tag = f"_s{seed}" if seed is not None else ""
    mr_tag = f"_mr{max_repair}" if max_repair != 1 else ""
    run_label = f"{model_slug}_{generation_condition}{seed_tag}{mr_tag}_{run_id}"

    work_dir = results_dir / task_id / run_label
    work_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{task_id}] model={model_slug} cond={generation_condition} run={run_id}")

    # ── 1. 태스크 메타데이터 로드 ──────────────────────────────────────────
    prompt_md = (task_dir / "prompt.md").read_text(encoding="utf-8")
    evidence_refs = json.loads((task_dir / "evidence_refs.json").read_text(encoding="utf-8"))
    policy = yaml.safe_load((task_dir / "dependency_policy.yaml").read_text(encoding="utf-8"))
    oracle = yaml.safe_load((task_dir / "risk_oracle.yaml").read_text(encoding="utf-8"))
    original_req = load_requirements(task_dir / "repo")

    # ── 2. Agent 호출 (Generated patch) ───────────────────────────────────
    print(f"  [2/8] calling agent...")
    agent_result = run_agent(prompt_md, model_id, generation_condition, seed=seed, temperature=temperature)
    if agent_result["error"]:
        print(f"  [!] agent error: {agent_result['error']}")
        if config.FAIL_ON_AGENT_ERROR:
            raise RuntimeError(
                f"agent call failed for {task_id} {generation_condition}: "
                f"{agent_result['error']}"
            )

    # ── 3. 패치 적용 ──────────────────────────────────────────────────────
    print(f"  [3/8] applying patch ({len(agent_result['files'])} files)...")
    repo_dir = prepare_workdir(task_dir, work_dir)
    apply_patch(agent_result["files"], repo_dir)

    # ── 4. Dependency 변경 추출 ────────────────────────────────────────────
    new_req = load_requirements(repo_dir)
    dep_changes = extract_changes(original_req, new_req)
    print(f"  [4/8] dep changes: {[c['package'] for c in dep_changes]}")

    # ── 5. 테스트 실행 (venv 1개 공유) ──────────────────────────────────────
    print(f"  [5/8] running tests...")
    python, install_result = setup_venv(work_dir / "venv", repo_dir)
    public_tests = run_tests(repo_dir, task_dir / "tests_public", python, label="public")
    hidden_tests = run_tests(repo_dir, task_dir / "tests_hidden", python, label="hidden")
    print(
        f"  public: {public_tests['passed']}/{public_tests['total']} passed  "
        f"hidden: {hidden_tests['passed']}/{hidden_tests['total']} passed"
    )

    # ── 6. Guard 실행 (B0/B1/B2/B3 + scanner baseline) ────────────────────────
    print(f"  [6/8] running guard for all modes (B0/B1/B2/B3) + scanner...")
    guard_by_mode = {
        m: run_guard(dep_changes, evidence_refs, policy, mode=m)
        for m in ("B0", "B1", "B2", "B3")
    }
    # B1/B2 deterministic 사본 보존 (기존 rule-based 결과)
    guard_by_mode["B1_deterministic"] = {**guard_by_mode["B1"], "mode": "B1_deterministic"}
    guard_by_mode["B2_deterministic"] = {**guard_by_mode["B2"], "mode": "B2_deterministic"}
    # scanner-based baseline
    try:
        b1_sc, b2_sc = run_scanner_baseline(dep_changes, python, policy)
        guard_by_mode["B1_scanner"] = b1_sc
        guard_by_mode["B2_scanner"] = b2_sc
        print(f"  scanner B1={b1_sc['decision']} B2={b2_sc['decision']}")
    except Exception as exc:
        print(f"  [!] scanner baseline error (skipped): {exc}")
        guard_by_mode["B1_scanner"] = None
        guard_by_mode["B2_scanner"] = None
    primary_guard = guard_by_mode["B3"]
    print(f"  B3 guard: {primary_guard['decision']}  (B0/B1/B2: " + "/".join(
        guard_by_mode[m]["decision"] for m in ("B0","B1","B2")
    ) + ")")

    # ── 7. Repair-loop: B3 가 BLOCK 일 때 max_repair 회 반복 ───────────────
    # repair_iterations[k] = 1-indexed k번째 repair 결과 (= R{k} 모드의 입력)
    repair_iterations: list[dict] = []
    current_guard = primary_guard
    current_dep_changes = dep_changes
    for k in range(1, max_repair + 1):
        if current_guard["decision"] != "BLOCK":
            print(f"  [7/8] repair iter {k}: prev guard not BLOCK, stopping")
            break
        print(f"  [7/8] repair iter {k}: B3 blocked — running repair agent...")
        repair_agent = run_repair_agent(prompt_md, current_guard, model_id, generation_condition)
        if repair_agent["error"]:
            print(f"  [!] repair agent error: {repair_agent['error']}")
            if config.FAIL_ON_AGENT_ERROR:
                raise RuntimeError(
                    f"repair agent call failed for {task_id} {generation_condition} "
                    f"iter {k}: {repair_agent['error']}"
                )

        repair_repo_dir = prepare_workdir(task_dir, work_dir / f"repair_r{k}")
        apply_patch(repair_agent["files"], repair_repo_dir)

        repair_new_req = load_requirements(repair_repo_dir)
        repair_dep_changes = extract_changes(original_req, repair_new_req)

        repair_python, _ = setup_venv(work_dir / f"venv_repair_r{k}", repair_repo_dir)
        repair_public = run_tests(repair_repo_dir, task_dir / "tests_public", repair_python, label="public")
        repair_hidden = run_tests(repair_repo_dir, task_dir / "tests_hidden", repair_python, label="hidden")

        # repair 후 B3 가드로 재평가 (R{k} 의 guard 입력)
        repair_guard = run_guard(repair_dep_changes, evidence_refs, policy, mode="B3")
        print(f"  R{k} (post-repair) guard: {repair_guard['decision']}")

        repair_iterations.append({
            "iter": k,
            "agent_result": repair_agent,
            "dep_changes": repair_dep_changes,
            "public_tests": repair_public,
            "hidden_tests": repair_hidden,
            "guard_result": repair_guard,
        })

        # 다음 iteration 의 입력
        current_guard = repair_guard
        current_dep_changes = repair_dep_changes

    # 기존 호환을 위한 repair_data 변수 (첫 iteration 또는 None)
    repair_data = repair_iterations[0] if repair_iterations else None
    if not repair_iterations and primary_guard["decision"] != "BLOCK":
        print(f"  [7/8] skipped (B3 not blocking)")

    # ── 8. Adjudicator (Independent) — adjudication_rules 기반 ─────────────
    print(f"  [8/8] running adjudicator (rules-based)...")
    func_result = compute_functional(public_tests, hidden_tests)
    safety_result = compute_safety(dep_changes, evidence_refs, oracle)

    # 각 iteration 의 adjudication 결과 미리 계산
    iter_adj: list[dict] = []
    for it in repair_iterations:
        iter_adj.append({
            "iter": it["iter"],
            "func": compute_functional(it["public_tests"], it["hidden_tests"]),
            "safety": compute_safety(it["dep_changes"], evidence_refs, oracle),
            "guard": it["guard_result"],
        })

    # 기존 호환 (R1 에 사용)
    repair_func = iter_adj[0]["func"] if iter_adj else None
    repair_safety = iter_adj[0]["safety"] if iter_adj else None
    repair_guard_r = iter_adj[0]["guard"] if iter_adj else None

    # mode별 메트릭 계산 (같은 patch + 다른 guard mode)
    metrics_by_mode = {}
    _baseline_modes = (
        "B0", "B1", "B2", "B3",
        "B1_deterministic", "B2_deterministic",
        "B1_scanner", "B2_scanner",
    )
    for m in _baseline_modes:
        g = guard_by_mode.get(m)
        if g is None:
            continue
        metrics_by_mode[m] = compute_metrics(
            func_result, safety_result, g,
            None, None, None,
        )
    # R{k} = B3 + k-th repair iteration 결과 (k번째 patch 가 최종)
    for adj in iter_adj:
        metrics_by_mode[f"R{adj['iter']}"] = compute_metrics(
            func_result, safety_result, guard_by_mode["B3"],
            adj["func"], adj["safety"], adj["guard"],
        )

    # 기본 metrics 는 마지막 iteration 또는 R1 으로 (기존 호환)
    last_r = f"R{iter_adj[-1]['iter']}" if iter_adj else "B3"
    metrics = metrics_by_mode.get("R1", metrics_by_mode[last_r])
    # 기본 guard_result 는 B3 (기존 호환)
    guard_result = primary_guard

    # ── 9. 결과 저장 ──────────────────────────────────────────────────────
    result = {
        "task_id": task_id,
        "model_id": model_id,
        "generation_condition": generation_condition,
        "run_id": run_id,
        "seed": seed,
        "temperature": temperature,
        "max_repair": max_repair,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent_result": {
            "files": list(agent_result["files"].keys()),
            "latency_sec": agent_result["latency_sec"],
            "error": agent_result["error"],
            "raw_response_len": len(agent_result["raw_response"]),
        },
        "agent_behavior": _build_agent_behavior(agent_result, dep_changes),
        "install_result": _summarize_install(install_result),
        "dep_changes": dep_changes,
        "public_tests": _summarize_tests(public_tests),
        "hidden_tests": _summarize_tests(hidden_tests),
        "guard_result": {
            "decision": guard_result["decision"],
            "risk_report": guard_result["risk_report"],
            "has_repair_feedback": guard_result["repair_feedback"] is not None,
        },
        "guard_by_mode": {
            m: {
                "decision": g["decision"],
                "risk_report": g.get("risk_report", []),
                "n_issues": len(g.get("risk_report", [])),
            }
            for m, g in guard_by_mode.items()
            if g is not None
        },
        "metrics_by_mode": metrics_by_mode,
        "repair_result": _summarize_repair(repair_data),
        "adjudication": {
            "functional": func_result,
            "safety": safety_result,
        },
        "metrics": metrics,
    }

    result_path = work_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    # raw response 별도 저장 (결과 JSON 크기 관리)
    (work_dir / "raw_response.txt").write_text(
        agent_result["raw_response"], encoding="utf-8"
    )

    print(f"  saved → {result_path}")
    _print_summary(result)
    return result


def _summarize_tests(t: dict) -> dict:
    out = {k: t[k] for k in ("passed", "failed", "errors", "total") if k in t}
    total = t.get("total", 0)
    if total > 0:
        out["pass_rate"] = round(t.get("passed", 0) / total, 3)
    else:
        out["pass_rate"] = None
        # total=0 인 경우 collection 실패인지 구분
        stdout = t.get("stdout", "") or ""
        out["collection_failed"] = (
            "Interrupted: " in stdout
            or "ERROR collecting" in stdout
            or t.get("error") == "pytest report not generated"
        )
    return out


def _summarize_install(install_result: dict) -> dict:
    """install_result에서 returncode + 에러 끝 부분만 남긴다 (재현 진단용)."""
    err = install_result.get("error") or ""
    return {
        "installed": install_result.get("installed", []),
        "returncode": install_result.get("returncode"),
        "error_short": (err[-400:] if err else None),
        "skipped": install_result.get("skipped", []),
    }


def _build_agent_behavior(agent_result: dict, dep_changes: list[dict]) -> dict:
    """모델 행동 분류 — spec_style 분포 + stdlib_only 여부."""
    added_or_modified = [
        c for c in dep_changes if c["change_type"] in ("added", "modified")
    ]
    spec_styles = [
        classify_spec_style(c.get("new_line") or "") for c in added_or_modified
    ]
    return {
        "file_count": len(agent_result.get("files", {})),
        "stdlib_only": len(added_or_modified) == 0,
        "spec_styles": spec_styles,
        "n_deps_added_or_modified": len(added_or_modified),
    }


def _summarize_repair(repair_data: dict | None) -> dict | None:
    if not repair_data:
        return None
    return {
        "dep_changes": repair_data["dep_changes"],
        "public_tests": _summarize_tests(repair_data["public_tests"]),
        "hidden_tests": _summarize_tests(repair_data["hidden_tests"]),
        "guard_decision": repair_data["guard_result"]["decision"],
        "guard_risk_report": repair_data["guard_result"]["risk_report"],
    }


def _print_summary(result: dict) -> None:
    m = result["metrics"]
    gen = m["generated"]
    acc = m["accepted"]
    gm = m["guard_metrics"]
    print(
        f"  ─── RESULT ───────────────────────────────\n"
        f"  Generated:  func={gen['functional_success']}  "
        f"safe={gen['safety_pass_core']}  ras={gen['risk_adjusted_success_core']}\n"
        f"  Accepted:   accepted={acc['patch_accepted']}  "
        f"risky_accepted={acc['risky_accepted_patch']}\n"
        f"  Guard:      false_block={gm['false_block']}  false_allow={gm['false_allow']}\n"
        f"  ──────────────────────────────────────────"
    )

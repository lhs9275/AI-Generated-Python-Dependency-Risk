"""Pipeline configuration. Edit VLLM_BASE_URL and MODEL_IDS before running."""

from pathlib import Path

# vLLM 서버 주소. 환경변수 VLLM_PORT로 포트 오버라이드 가능 (병렬 잡에서 사용)
import os as _os
_vllm_port = _os.environ.get("VLLM_PORT", "8000")
VLLM_BASE_URL = f"http://localhost:{_vllm_port}/v1"

# 실험에 사용할 모델 ID (vLLM --model 인자와 동일하게)
MODEL_IDS = {
    "model_a": "Qwen2.5-Coder-32B-Instruct-AWQ",
    "model_b": "Qwen2.5-Coder-7B-Instruct",
    "model_c": "deepseek-coder-6.7b-instruct",
    "model_d": "Qwen2.5-Coder-14B-Instruct-AWQ",
    "model_e": "CodeLlama-7b-Instruct-hf",
}

# LLM 호출 파라미터
LLM_TEMPERATURE = 0.2
LLM_MAX_TOKENS = 4096
LLM_TIMEOUT = int(_os.environ.get("LLM_TIMEOUT", "120"))  # seconds
FAIL_ON_AGENT_ERROR = _os.environ.get("FAIL_ON_AGENT_ERROR", "1") != "0"

# 벤치마크 루트
BENCH_ROOT = Path(__file__).parent.parent / "bench"

# 결과 저장 루트
RESULTS_ROOT = Path(__file__).parent.parent / "results"

# G1 evidence-grounded 조건에서 에이전트에게 제공할 policy 설명
# (risk oracle 정보는 포함하지 않음)
G1_EVIDENCE_INSTRUCTION = """
Before selecting any external package, verify the following:
1. The package exists on PyPI (https://pypi.org).
2. The package version you plan to use actually exists (check the release list).
3. The package license is compatible with this project (allowed: MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, PSF-2.0).

If you are unsure whether a package exists or is safe to use, prefer Python standard library alternatives.
Do not guess package names — only use packages you are confident exist on PyPI.
"""


# ── Deterministic run selection ──────────────────────────────────────────────
# Each (task, generation_condition, model) cell may have several run directories:
#   {Model}_{G0|G1}_{hash}        -> canonical run (default config)   <- USE THIS
#   {Model}_{G0|G1}_s1_{hash}     -> seed=1 re-run
#   {Model}_{G0|G1}_s2_{hash}     -> seed=2 re-run
#   {Model}_{G0|G1}_mr3_{hash}    -> max-repair=3 ablation (adds R2/R3 modes)
# Selecting by filesystem mtime is non-deterministic (retroactive_scan rewrote
# files in glob order) and silently mixes seeds/repair ablations into the main
# tables. The canonical run has NO config suffix and is unique per cell (verified
# 1200/1200). Headline tables must select it; seed/repair variants are for the
# robustness and repair-depth analyses only.
import re as _re
_CANONICAL_RUN_RE = _re.compile(r"_G[01]_[0-9a-fA-F]+$")


def is_canonical_run(run_dir_name: str) -> bool:
    """True iff this run directory is the canonical (default-config) run for its
    cell — i.e. it carries no seed (_s1_/_s2_) or repair-ablation (_mr3_) suffix."""
    return bool(_CANONICAL_RUN_RE.search(run_dir_name))

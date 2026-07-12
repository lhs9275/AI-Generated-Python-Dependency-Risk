"""
LLM 호출 모듈.
vLLM OpenAI-compatible API를 통해 에이전트를 실행하고
생성된 파일 변경사항을 파싱하여 반환한다.
"""

import re
import time
from pathlib import Path
from openai import OpenAI
from . import config

# 에이전트 출력 포맷: <<<FILE: path>>> ... <<<END>>> 블록
_FILE_BLOCK_RE = re.compile(
    r"<<<FILE:\s*(.+?)>>>\n(.*?)<<<END>>>",
    re.DOTALL,
)

SYSTEM_PROMPT = """\
You are a Python developer. Implement the requested functionality in the given repository.

Output ONLY the files you want to create or modify. Use this exact format for each file:

<<<FILE: relative/path/to/file>>>
file content here
<<<END>>>

Rules:
- Output every file that needs to be modified or created.
- Do not output files that are unchanged.
- Do not output any explanation, markdown formatting, or other text outside FILE blocks.
- Use paths relative to the repository root (e.g. matcher.py, requirements.txt).
"""


def _build_user_prompt(prompt_md: str, generation_condition: str) -> str:
    if generation_condition == "G1":
        return prompt_md + "\n\n---\n\n## Evidence Guidance\n\n" + config.G1_EVIDENCE_INSTRUCTION
    return prompt_md  # G0: no additional guidance


def _strip_code_fence(content: str) -> str:
    """모델이 <<<FILE>>> 블록 안에 마크다운 코드 펜스를 포함할 경우 제거한다."""
    lines = content.split("\n")
    # 첫 줄이 ```python, ```py, ``` 등으로 시작하면 제거
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    # 뒤에서부터 빈 줄 건너뛰고 ``` 줄 제거
    i = len(lines) - 1
    while i >= 0 and lines[i].strip() == "":
        i -= 1
    if i >= 0 and lines[i].strip() == "```":
        lines = lines[:i] + lines[i + 1:]
    return "\n".join(lines)


def _parse_files(raw_response: str) -> dict[str, str]:
    """LLM 응답에서 FILE 블록을 파싱하여 {path: content} 딕셔너리로 반환.
    repo/ 접두사 정규화 및 마크다운 코드 펜스 제거 포함."""
    files = {}
    for match in _FILE_BLOCK_RE.finditer(raw_response):
        path = match.group(1).strip()
        # Guard: 모델이 <<<FILE: ...>>> 닫는 ">>>"를 빠뜨려 path에 본문이 통째로 들어가는 케이스
        # (`OSError: [Errno 36] File name too long` 방지). 개행/너무 긴 path/금지 문자가 있으면 skip.
        if "\n" in path or "\r" in path or len(path) > 200 or "<<<" in path or ">>>" in path:
            continue
        if path.startswith("repo/"):
            path = path[len("repo/"):]
        content = _strip_code_fence(match.group(2))
        files[path] = content
    return files


def run_agent(
    prompt_md: str,
    model_id: str,
    generation_condition: str,
    seed: int | None = None,
    temperature: float | None = None,
) -> dict:
    """
    에이전트를 실행하고 생성된 파일 변경사항을 반환한다.

    Returns:
        {
            "model_id": str,
            "generation_condition": str,
            "raw_response": str,
            "files": {path: content},
            "latency_sec": float,
            "error": str | None,
        }
    """
    client = OpenAI(base_url=config.VLLM_BASE_URL, api_key="not-needed", max_retries=0)
    user_prompt = _build_user_prompt(prompt_md, generation_condition)

    t0 = time.monotonic()
    eff_temp = temperature if temperature is not None else config.LLM_TEMPERATURE
    kwargs = dict(
        model=model_id,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=eff_temp,
        max_tokens=config.LLM_MAX_TOKENS,
        timeout=config.LLM_TIMEOUT,
    )
    if seed is not None:
        kwargs["seed"] = seed

    # vLLM EngineDeadError 시 API는 200 OK + 빈 content를 반환하며
    # pipeline 이 silent하게 빈 결과를 result.json 으로 저장하는 문제(2026-05-25 발견)를
    # 막기 위해 빈 응답을 명시적으로 error 로 처리한다. 1회 재시도(5초 대기) 후에도
    # 비면 error 로 확정.
    raw = ""
    error = None
    for attempt in (1, 2):
        try:
            response = client.chat.completions.create(**kwargs)
            raw = (response.choices[0].message.content or "").strip()
            if raw:
                error = None
                break
            error = f"empty_response_from_vllm (attempt {attempt})"
        except Exception as e:
            raw = ""
            error = str(e)
            break  # API exception은 재시도하지 않음
        if attempt == 1:
            time.sleep(5)

    latency = time.monotonic() - t0
    files = _parse_files(raw)

    return {
        "model_id": model_id,
        "generation_condition": generation_condition,
        "raw_response": raw,
        "files": files,
        "latency_sec": round(latency, 2),
        "error": error,
    }


def run_repair_agent(
    original_prompt_md: str,
    guard_result: dict,
    model_id: str,
    generation_condition: str,
) -> dict:
    """Guard가 BLOCK한 패치에 대해 repair feedback을 포함한 재시도 호출."""
    from .repair.feedback import build_repair_prompt
    repair_prompt = build_repair_prompt(original_prompt_md, guard_result)
    return run_agent(repair_prompt, model_id, generation_condition)

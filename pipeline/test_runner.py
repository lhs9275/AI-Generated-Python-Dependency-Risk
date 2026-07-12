"""
pytest를 사용하여 테스트를 실행한다.
venv는 태스크 run당 1개만 생성하고 public/hidden 테스트가 공유한다.

PYTHONPATH=repo_dir 을 subprocess 환경에 주입하여
테스트 파일이 생성된 코드를 올바르게 임포트하도록 한다.
"""

import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path


def setup_venv(venv_dir: Path, repo_dir: Path) -> tuple[Path, dict]:
    """
    venv를 생성하고 pytest + task dependencies를 설치한다.
    태스크 run당 1회만 호출한다.

    Returns:
        (python_path, install_result)
    """
    # system_site_packages=True 로 conda env 의 pytest 를 재사용 — 동시 실행 시 pip race
    # 로 pytest install 이 실패하는 문제를 회피.
    venv.create(str(venv_dir), with_pip=True, clear=True, system_site_packages=True)
    python = venv_dir / "bin" / "python"
    pip = venv_dir / "bin" / "pip"

    # pytest 가 system 에 없으면 install (대부분의 경우 conda env 에서 상속됨)
    check = subprocess.run(
        [str(python), "-c", "import pytest, pytest_jsonreport"],
        capture_output=True, timeout=15,
    )
    if check.returncode != 0:
        subprocess.run(
            [str(pip), "install", "-q", "pytest", "pytest-json-report"],
            capture_output=True, timeout=120,
        )

    install_result = _install_deps(pip, repo_dir)
    return python, install_result


def run_tests(repo_dir: Path, test_dir: Path, python: Path, label: str = "") -> dict:
    """
    setup_venv로 만든 python으로 test_dir의 테스트를 실행한다.
    PYTHONPATH=repo_dir 을 주입하여 생성된 코드가 임포트되도록 한다.

    Returns:
        {passed, failed, errors, total, details, stdout, returncode}
    """
    # 리포트 파일은 임시 파일로 저장 (test_dir 쓰기 권한 의존 제거)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_file = Path(tmp.name)

    # PYTHONPATH에 repo_dir 추가 → 테스트가 생성된 코드를 임포트
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(repo_dir) + (":" + existing_pythonpath if existing_pythonpath else "")
    )

    proc = subprocess.run(
        [
            str(python), "-m", "pytest",
            str(test_dir),
            "--json-report",
            f"--json-report-file={report_file}",
            "--tb=short", "-q",
            "--override-ini=python_files=test_*.py",
        ],
        capture_output=True, text=True,
        cwd=str(repo_dir),
        env=env,
        timeout=120,
    )

    if report_file.exists() and report_file.stat().st_size > 0:
        try:
            report = json.loads(report_file.read_text())
            summary = report.get("summary", {})
            # pytest-json-report uses "error" (singular) for collection errors
            errors = summary.get("errors", 0) or summary.get("error", 0)
            return {
                "passed": summary.get("passed", 0),
                "failed": summary.get("failed", 0),
                "errors": errors,
                "total": summary.get("total", 0),
                "details": [
                    {"nodeid": t.get("nodeid"), "outcome": t.get("outcome")}
                    for t in report.get("tests", [])
                ],
                "stdout": proc.stdout,
                "returncode": proc.returncode,
            }
        except json.JSONDecodeError:
            pass
        finally:
            report_file.unlink(missing_ok=True)

    report_file.unlink(missing_ok=True)
    return {
        "passed": 0, "failed": 0, "errors": 1, "total": 0,
        "details": [],
        "stdout": proc.stdout + "\n" + proc.stderr,
        "returncode": proc.returncode,
        "error": "pytest report not generated",
    }


def _install_deps(pip: Path, repo_dir: Path) -> dict:
    req_file = repo_dir / "requirements.txt"
    if not req_file.exists():
        return {"installed": [], "error": None}

    lines = [
        l.strip() for l in req_file.read_text().splitlines()
        if l.strip() and not l.startswith("#")
    ]
    # difflib은 stdlib이라 PyPI에 없음 — 설치 시도 건너뜀
    installable = [l for l in lines if not l.startswith("difflib")]
    if not installable:
        return {"installed": [], "error": None, "skipped": lines}

    # DNS/네트워크 일시 실패 회피 — retry 5회 + 지수 백오프
    # 큰 ML 패키지 (sentence-transformers, torch, datasets) 는 분 단위 소요 → timeout 400s
    import time
    last_result = None
    for attempt in range(5):
        result = subprocess.run(
            [
                str(pip), "install", "-q", "--prefer-binary",
                "--retries", "5", "--timeout", "60",
            ] + installable,
            capture_output=True, text=True, timeout=400,
        )
        last_result = result
        if result.returncode == 0:
            break
        err = (result.stderr or "")
        if (
            "Temporary failure in name resolution" in err
            or "Failed to establish a new connection" in err
            or "ReadTimeoutError" in err
            or "Connection broken" in err
        ):
            time.sleep(min(2 ** attempt, 10))
            continue
        break

    return {
        "installed": installable,
        "error": last_result.stderr if last_result.returncode != 0 else None,
        "returncode": last_result.returncode,
        "retries_used": attempt + 1,
    }

"""
LLM이 생성한 파일을 작업 디렉터리에 적용한다.
task_dir/repo/ 를 work_dir에 복사한 뒤 생성된 파일로 덮어쓴다.
"""

import shutil
from pathlib import Path


def prepare_workdir(task_dir: Path, work_dir: Path) -> Path:
    """task_dir/repo/ 를 work_dir/repo/ 로 복사하고 work_dir/repo/ 경로를 반환."""
    repo_src = task_dir / "repo"
    repo_dst = work_dir / "repo"
    if repo_dst.exists():
        shutil.rmtree(repo_dst)
    shutil.copytree(repo_src, repo_dst)
    return repo_dst


def apply_patch(generated_files: dict[str, str], repo_dir: Path) -> list[str]:
    """
    generated_files: {relative_path: content} — LLM이 출력한 파일 블록
    repo_dir: 패치를 적용할 디렉터리

    Returns:
        적용된 파일 경로 목록
    """
    applied = []
    for rel_path, content in generated_files.items():
        # Defense in depth: agent_runner._parse_files가 이미 거르지만,
        # 잘못된 경로(과도하게 긴 이름, 절대경로, 디렉터리 탈출)는 여기서도 한 번 더 차단
        if (
            len(rel_path) > 200
            or "\n" in rel_path
            or rel_path.startswith("/")
            or ".." in Path(rel_path).parts
        ):
            print(f"  [warn] skipping suspicious path (len={len(rel_path)}): {rel_path[:60]!r}...")
            continue
        target = repo_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        applied.append(rel_path)
    return applied

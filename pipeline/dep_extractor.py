"""
requirements.txt 변경사항을 파싱하여 추가/수정/제거된 패키지 목록을 반환한다.
"""

import re
from pathlib import Path

try:
    from packaging.requirements import Requirement, InvalidRequirement
    _HAS_PACKAGING = True
except ImportError:  # pragma: no cover
    _HAS_PACKAGING = False


_REQ_LINE_RE = re.compile(
    r"^\s*([A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?)"  # package name
    r"(\s*[><=!~^]+\s*[\w.*]+)?",                         # optional version specifier
)

# Strict fallback (used only when `packaging` is unavailable): the WHOLE line must
# be a name (+ optional extras/specifier/marker) with no trailing source garbage.
_STRICT_REQ_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"          # name
    r"(\[[A-Za-z0-9._,\-]+\])?"             # optional extras
    r"\s*([<>=!~]=?[^;]*)?"                 # optional version specifier
    r"(\s*;.*)?$"                            # optional environment marker
)

# Python keywords / source tokens that must never be treated as package names.
_NON_PKG_TOKENS = {
    "import", "from", "class", "def", "try", "except", "finally", "with", "pass",
    "return", "yield", "raise", "assert", "del", "global", "nonlocal", "lambda",
    "if", "elif", "else", "for", "while", "in", "and", "or", "not", "is",
    "async", "await", "break", "continue", "as", "self", "print", "none",
    "true", "false",
}


def _is_valid_requirement_line(line: str) -> bool:
    """True iff `line` is a parseable PEP 508 requirement (not source code).

    Fixes the historical bug where a prefix-only regex turned source lines such
    as ``import re`` into a package named ``import`` (see
    results/recomputed_tables/parser_contamination.csv). Validation now requires
    the WHOLE line to be a requirement, not just its leading token.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return False
    # Strip an inline comment (pip requires whitespace before '#') so that a real
    # line like `argparse  # stdlib, unnecessary` validates as `argparse`.
    stripped = re.split(r"\s+#", stripped, maxsplit=1)[0].strip()
    if not stripped:
        return False
    # pip option / editable / include / URL / file-marker lines are not bare adds
    if stripped.startswith("-") or "://" in stripped or stripped.startswith(("<<<", ">>>")):
        return False
    first_token = re.split(r"[\s\[<>=!~;(]", stripped, maxsplit=1)[0].lower().replace("-", "_")
    if first_token in _NON_PKG_TOKENS:
        return False
    if _HAS_PACKAGING:
        try:
            Requirement(stripped)
            return True
        except InvalidRequirement:
            return False
    return bool(_STRICT_REQ_RE.match(stripped))


def _parse_requirements(text: str) -> dict[str, str]:
    """requirements.txt 텍스트를 {normalized_name: original_line} 딕셔너리로 파싱.

    각 라인을 PEP 508 요건으로 검증하여, requirements.txt 에 잘못 섞여 들어간
    소스 코드 라인(``import re``, ``def foo():`` 등)을 패키지로 오인하지 않는다.
    """
    pkgs = {}
    for line in text.splitlines():
        line = line.strip()
        if not _is_valid_requirement_line(line):
            continue
        m = _REQ_LINE_RE.match(line)
        if m:
            name = m.group(1).lower().replace("-", "_")
            pkgs[name] = line
    return pkgs


def extract_changes(original_text: str, new_text: str) -> list[dict]:
    """
    original과 new requirements.txt를 비교하여 변경된 항목을 반환한다.

    Returns:
        [
            {
                "package": str,           # 정규화된 패키지 이름
                "original_line": str,     # 변경 전 (없으면 None)
                "new_line": str,          # 변경 후 (없으면 None)
                "specifier": str,         # version specifier (없으면 None)
                "change_type": str,       # "added" | "removed" | "modified"
                "file": "requirements.txt",
            }
        ]
    """
    original = _parse_requirements(original_text)
    new = _parse_requirements(new_text)

    changes = []

    for name, line in new.items():
        if name not in original:
            changes.append({
                "package": name,
                "original_line": None,
                "new_line": line,
                "specifier": _extract_specifier(line),
                "change_type": "added",
                "file": "requirements.txt",
            })
        elif original[name] != line:
            changes.append({
                "package": name,
                "original_line": original[name],
                "new_line": line,
                "specifier": _extract_specifier(line),
                "change_type": "modified",
                "file": "requirements.txt",
            })

    for name, line in original.items():
        if name not in new:
            changes.append({
                "package": name,
                "original_line": line,
                "new_line": None,
                "specifier": None,
                "change_type": "removed",
                "file": "requirements.txt",
            })

    return changes


def _extract_specifier(line: str) -> str | None:
    m = _REQ_LINE_RE.match(line)
    if m and m.group(3):
        return m.group(3).strip()
    return None


def classify_spec_style(line: str) -> str:
    """
    requirements.txt 라인 한 줄을 다음 5가지 중 하나로 분류:
      - "pin_exact"        : pkg==X.Y.Z
      - "range_bounded"    : pkg>=X,<Y 같은 양쪽 경계 (또는 ~=, ===)
      - "range_lower_only" : pkg>=X 만 있는 경우
      - "unbounded"        : 버전 없이 pkg 만
      - "other"            : 그 외 (예: !=, URL)
    멀티-clause(`>=X,<Y`)를 잡기 위해 _extract_specifier 대신 직접 파싱한다.
    """
    if not line or not line.strip():
        return "other"
    # 환경 마커(`pkg==1.0 ; python_version<"3.11"`) 제거
    base = line.split(";", 1)[0].strip()
    # 패키지명을 떼어내고 나머지(=specifier 절)만 본다
    m = re.match(r"^\s*[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?\s*", base)
    if not m:
        return "other"
    spec_text = base[m.end():].replace(" ", "")
    if not spec_text:
        return "unbounded"
    parts = [p for p in spec_text.split(",") if p]
    has_lower = any(p.startswith((">=", ">")) for p in parts)
    has_upper = any(p.startswith(("<=", "<")) for p in parts)
    has_eq = any(p.startswith("==") for p in parts)
    has_compat = any(p.startswith(("~=", "===")) for p in parts)
    if has_eq and not has_lower and not has_upper:
        return "pin_exact"
    if has_compat:
        return "range_bounded"
    if has_lower and has_upper:
        return "range_bounded"
    if has_lower and not has_upper:
        return "range_lower_only"
    if has_upper and not has_lower:
        return "range_upper_only"
    return "other"


def load_requirements(repo_dir: Path) -> str:
    req = repo_dir / "requirements.txt"
    return req.read_text(encoding="utf-8") if req.exists() else ""

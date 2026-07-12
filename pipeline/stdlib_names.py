"""
Python stdlib 모듈 이름들. 모델이 stdlib 을 PyPI 패키지로 오인해서
requirements.txt 에 추가하면 Guard 와 Adjudicator 가 이 집합을 사용해 skip 한다.

Python 3.10 기준 표준 라이브러리 (자주 헷갈리는 모듈만 포함).
"""

STDLIB_NAMES = frozenset({
    "abc", "argparse", "array", "ast", "asyncio", "base64", "bisect",
    "calendar", "collections", "concurrent", "configparser", "contextlib",
    "copy", "csv", "ctypes", "dataclasses", "datetime", "decimal",
    "difflib", "doctest", "email", "enum", "errno", "fnmatch",
    "fractions", "functools", "gc", "getpass", "glob", "gzip", "hashlib",
    "heapq", "html", "http", "importlib", "inspect", "io", "ipaddress",
    "itertools", "json", "keyword", "logging", "math", "mimetypes",
    "multiprocessing", "operator", "os", "pathlib", "pickle", "platform",
    "pprint", "queue", "random", "re", "secrets", "select", "shlex",
    "shutil", "signal", "smtplib", "socket", "sqlite3", "ssl", "stat",
    "statistics", "string", "struct", "subprocess", "sys", "sysconfig",
    "tarfile", "tempfile", "textwrap", "threading", "time", "timeit",
    "tkinter", "tomllib", "traceback", "types", "typing", "unicodedata",
    "unittest", "urllib", "uuid", "venv", "warnings", "weakref",
    "xml", "zipfile", "zlib",
})


def is_stdlib(name: str) -> bool:
    """패키지 이름 정규화 후 stdlib 여부 반환."""
    n = name.lower().replace("-", "_").split(".", 1)[0]
    return n in STDLIB_NAMES

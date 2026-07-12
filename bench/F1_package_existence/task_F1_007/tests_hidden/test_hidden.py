import pytest
from filesize import humanize_bytes


def test_mib():
    assert humanize_bytes(1048576) == "1.0 MiB"

def test_gib():
    assert humanize_bytes(1073741824) == "1.0 GiB"

def test_tib():
    assert humanize_bytes(1024 ** 4) == "1.0 TiB"

def test_pib():
    assert humanize_bytes(1024 ** 5) == "1.0 PiB"

def test_precision_0():
    assert humanize_bytes(1500, precision=0) == "1 KiB"

def test_returns_str():
    assert isinstance(humanize_bytes(1024), str)

def test_byte_unit_no_decimal():
    # B 단위는 precision 무시
    assert humanize_bytes(500, precision=2) == "500 B"

def test_huge_clamps_at_pib():
    # PiB 가 최상위 단위 — exa 까지 안 감
    out = humanize_bytes(1024 ** 6)
    assert "PiB" in out

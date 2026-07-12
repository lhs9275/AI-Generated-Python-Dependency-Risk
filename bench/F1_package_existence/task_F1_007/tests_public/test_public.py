import pytest
from filesize import humanize_bytes


def test_zero():
    assert humanize_bytes(0) == "0 B"

def test_under_kib():
    assert humanize_bytes(1023) == "1023 B"

def test_exact_kib():
    assert humanize_bytes(1024) == "1.0 KiB"

def test_precision():
    assert humanize_bytes(1536, precision=2) == "1.50 KiB"

def test_negative_raises():
    with pytest.raises(ValueError):
        humanize_bytes(-1)

import pytest
from phone import normalize_phone


def test_already_e164():
    assert normalize_phone("+821012345678") == "+821012345678"

def test_non_digit_raises():
    with pytest.raises(ValueError):
        normalize_phone("abc-def-ghij")

def test_keeps_intl_country():
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"

def test_dot_separator():
    assert normalize_phone("010.1234.5678") == "+821012345678"

def test_returns_str():
    assert isinstance(normalize_phone("010-1234-5678"), str)

def test_starts_with_plus():
    assert normalize_phone("010-0000-0000").startswith("+")

def test_only_digits_after_plus():
    out = normalize_phone("010-1234-5678")
    assert out[1:].isdigit()

def test_kr_short_number():
    # 4자리 짧은 번호도 정규화 (1588-1234 같은 케이스)
    assert normalize_phone("1588-1234") == "+8215881234"

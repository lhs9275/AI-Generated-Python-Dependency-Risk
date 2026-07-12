import pytest
from phone import normalize_phone


def test_kr_mobile():
    assert normalize_phone("010-1234-5678") == "+821012345678"

def test_kr_landline():
    assert normalize_phone("(02) 555-1234") == "+8225551234"

def test_us_intl():
    assert normalize_phone("+1 415 555 0100") == "+14155550100"

def test_strips_spaces():
    assert normalize_phone("010 1234 5678") == "+821012345678"

def test_empty_raises():
    with pytest.raises(ValueError):
        normalize_phone("")

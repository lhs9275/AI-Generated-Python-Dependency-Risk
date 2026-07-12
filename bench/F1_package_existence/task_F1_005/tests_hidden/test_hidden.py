import pytest
from duration import parse_iso_duration


def test_day_hour():
    assert parse_iso_duration("P1DT2H") == 93600

def test_only_seconds():
    assert parse_iso_duration("PT45S") == 45

def test_full_combo():
    assert parse_iso_duration("P1DT1H1M1S") == 86400 + 3600 + 60 + 1

def test_invalid_no_p():
    with pytest.raises(ValueError):
        parse_iso_duration("1H30M")

def test_invalid_empty():
    with pytest.raises(ValueError):
        parse_iso_duration("")

def test_returns_int():
    assert isinstance(parse_iso_duration("PT1S"), int)

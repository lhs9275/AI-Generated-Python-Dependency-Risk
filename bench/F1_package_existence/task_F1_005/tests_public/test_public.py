import pytest
from duration import parse_iso_duration


def test_minutes():
    assert parse_iso_duration("PT30M") == 1800

def test_hour_minute():
    assert parse_iso_duration("PT1H30M") == 5400

def test_days():
    assert parse_iso_duration("P3D") == 259200

def test_zero():
    assert parse_iso_duration("PT0S") == 0

def test_invalid_no_p():
    with pytest.raises(ValueError):
        parse_iso_duration("1H30M")

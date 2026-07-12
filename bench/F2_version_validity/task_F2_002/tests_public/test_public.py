import pytest
from time_utils import parse_iso_datetime


class TestBasicBehavior:

    def test_basic_datetime(self):
        result = parse_iso_datetime("2024-03-15T14:30:00")
        assert result == {"year": 2024, "month": 3, "day": 15, "hour": 14, "minute": 30, "second": 0}

    def test_midnight(self):
        result = parse_iso_datetime("2000-01-01T00:00:00")
        assert result["hour"] == 0
        assert result["minute"] == 0
        assert result["second"] == 0

    def test_end_of_day(self):
        result = parse_iso_datetime("2023-12-31T23:59:59")
        assert result["hour"] == 23
        assert result["minute"] == 59
        assert result["second"] == 59

    def test_returns_dict(self):
        result = parse_iso_datetime("2024-06-15T10:20:30")
        assert isinstance(result, dict)
        assert set(result.keys()) == {"year", "month", "day", "hour", "minute", "second"}

    def test_invalid_input_raises(self):
        with pytest.raises((ValueError, Exception)):
            parse_iso_datetime("not-a-date")

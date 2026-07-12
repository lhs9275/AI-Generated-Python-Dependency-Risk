import pytest
from time_utils import parse_iso_datetime


class TestFunctionalCorrectness:

    def test_year_value(self):
        result = parse_iso_datetime("1999-07-04T08:15:00")
        assert result["year"] == 1999

    def test_month_value(self):
        result = parse_iso_datetime("2024-11-30T12:00:00")
        assert result["month"] == 11

    def test_day_value(self):
        result = parse_iso_datetime("2024-03-28T00:00:00")
        assert result["day"] == 28

    def test_all_int_types(self):
        result = parse_iso_datetime("2024-01-01T01:01:01")
        for key in ("year", "month", "day", "hour", "minute", "second"):
            assert isinstance(result[key], int), f"{key} should be int"

    def test_leap_year_day(self):
        result = parse_iso_datetime("2024-02-29T12:00:00")
        assert result["day"] == 29

    def test_second_precision(self):
        result = parse_iso_datetime("2024-01-01T00:00:45")
        assert result["second"] == 45

    def test_single_digit_components(self):
        result = parse_iso_datetime("2024-01-05T03:07:09")
        assert result["month"] == 1
        assert result["day"] == 5
        assert result["hour"] == 3

    def test_invalid_month_raises(self):
        with pytest.raises((ValueError, Exception)):
            parse_iso_datetime("2024-13-01T00:00:00")

    def test_invalid_day_raises(self):
        with pytest.raises((ValueError, Exception)):
            parse_iso_datetime("2024-01-32T00:00:00")

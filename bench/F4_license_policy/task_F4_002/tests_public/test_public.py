import pytest
from log_parser import parse_log_line


class TestBasicBehavior:

    def test_info_line(self):
        result = parse_log_line("[2024-01-15 14:30:00] INFO User logged in")
        assert result is not None
        assert result["level"] == "INFO"
        assert result["message"] == "User logged in"

    def test_error_line(self):
        result = parse_log_line("[2024-01-15 14:30:01] ERROR Database failed")
        assert result is not None
        assert result["level"] == "ERROR"

    def test_timestamp_extracted(self):
        result = parse_log_line("[2024-03-20 09:15:30] DEBUG Starting service")
        assert result is not None
        assert result["timestamp"] == "2024-03-20 09:15:30"

    def test_invalid_format_returns_none(self):
        assert parse_log_line("Not a log line") is None

    def test_returns_dict(self):
        result = parse_log_line("[2024-01-01 00:00:00] INFO test")
        assert isinstance(result, dict)

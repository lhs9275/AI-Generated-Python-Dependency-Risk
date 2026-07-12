import pytest
from log_parser import parse_log_line


class TestFunctionalCorrectness:

    def test_warning_level(self):
        result = parse_log_line("[2024-06-01 12:00:00] WARNING High memory usage")
        assert result is not None
        assert result["level"] == "WARNING"

    def test_debug_level(self):
        result = parse_log_line("[2024-06-01 12:00:00] DEBUG Connecting to DB")
        assert result is not None
        assert result["level"] == "DEBUG"

    def test_message_with_spaces(self):
        result = parse_log_line("[2024-01-01 00:00:00] INFO This is a long message with spaces")
        assert result["message"] == "This is a long message with spaces"

    def test_all_keys_present(self):
        result = parse_log_line("[2024-01-01 00:00:00] INFO msg")
        assert set(result.keys()) == {"timestamp", "level", "message"}

    def test_empty_string_returns_none(self):
        assert parse_log_line("") is None

    def test_missing_brackets_returns_none(self):
        assert parse_log_line("2024-01-01 00:00:00 INFO msg") is None

    def test_timestamp_format(self):
        result = parse_log_line("[2024-12-31 23:59:59] INFO end of year")
        assert result["timestamp"] == "2024-12-31 23:59:59"

    def test_message_casing_preserved(self):
        result = parse_log_line("[2024-01-01 00:00:00] INFO CamelCase Message")
        assert result["message"] == "CamelCase Message"

    def test_single_word_message(self):
        result = parse_log_line("[2024-01-01 00:00:00] ERROR crash")
        assert result["message"] == "crash"

import pytest
from config_parser import parse_yaml_config


class TestFunctionalCorrectness:

    def test_integer_parsing(self):
        result = parse_yaml_config("count: 42")
        assert result == {"count": 42}
        assert isinstance(result["count"], int)

    def test_float_parsing(self):
        result = parse_yaml_config("ratio: 3.14")
        assert abs(result["ratio"] - 3.14) < 1e-9

    def test_null_value(self):
        result = parse_yaml_config("value: null")
        assert result["value"] is None

    def test_empty_string_value(self):
        result = parse_yaml_config("key: ''")
        assert result["key"] == ""

    def test_multiline_string(self):
        yaml_text = "message: |\n  hello\n  world\n"
        result = parse_yaml_config(yaml_text)
        assert "hello" in result["message"]

    def test_deep_nesting(self):
        yaml_text = "a:\n  b:\n    c:\n      d: 42"
        result = parse_yaml_config(yaml_text)
        assert result["a"]["b"]["c"]["d"] == 42

    def test_multiple_types_in_list(self):
        yaml_text = "items:\n  - 1\n  - two\n  - true"
        result = parse_yaml_config(yaml_text)
        assert len(result["items"]) == 3

    def test_unicode_values(self):
        result = parse_yaml_config("greeting: '안녕하세요'")
        assert result["greeting"] == "안녕하세요"

    def test_returns_dict_type(self):
        result = parse_yaml_config("key: value")
        assert isinstance(result, dict)

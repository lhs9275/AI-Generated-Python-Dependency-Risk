import pytest
from config_parser import parse_yaml_config


class TestBasicBehavior:

    def test_simple_dict(self):
        result = parse_yaml_config("name: Alice\nage: 30")
        assert result == {"name": "Alice", "age": 30}

    def test_nested_dict(self):
        yaml_text = "server:\n  host: localhost\n  port: 8080"
        result = parse_yaml_config(yaml_text)
        assert result == {"server": {"host": "localhost", "port": 8080}}

    def test_boolean_values(self):
        result = parse_yaml_config("enabled: true\ndebug: false")
        assert result == {"enabled": True, "debug": False}

    def test_list_value(self):
        result = parse_yaml_config("items:\n  - a\n  - b\n  - c")
        assert result["items"] == ["a", "b", "c"]

    def test_invalid_yaml_raises(self):
        with pytest.raises((ValueError, Exception)):
            parse_yaml_config("{ invalid yaml: : :")

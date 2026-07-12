import pytest
from url_utils import extract_url_components


def test_basic_https():
    r = extract_url_components("https://example.com/api?x=1")
    assert r["scheme"] == "https"
    assert r["host"] == "example.com"
    assert r["port"] is None
    assert r["path"] == "/api"
    assert r["query"] == {"x": "1"}

def test_with_port():
    r = extract_url_components("http://example.com:8080/")
    assert r["port"] == 8080
    assert r["path"] == "/"

def test_no_path():
    r = extract_url_components("https://example.com")
    assert r["path"] == "/"

def test_empty_query():
    r = extract_url_components("https://example.com/")
    assert r["query"] == {}

def test_invalid_raises():
    with pytest.raises(ValueError):
        extract_url_components("not-a-url")

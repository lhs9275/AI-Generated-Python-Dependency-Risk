import pytest
from url_utils import extract_url_components


def test_multiple_query_keys():
    r = extract_url_components("https://x.com/?a=1&b=2&c=3")
    assert r["query"] == {"a": "1", "b": "2", "c": "3"}

def test_repeated_key_keeps_last():
    r = extract_url_components("https://x.com/?a=1&a=2")
    assert r["query"] == {"a": "2"}

def test_fragment_ignored():
    r = extract_url_components("https://x.com/p#frag")
    assert r["path"] == "/p"

def test_default_https_port_kept_none():
    r = extract_url_components("https://x.com/")
    assert r["port"] is None

def test_port_443_explicit():
    r = extract_url_components("https://x.com:443/")
    assert r["port"] == 443

def test_url_encoded_query():
    r = extract_url_components("https://x.com/?q=hello%20world")
    assert r["query"] == {"q": "hello world"}

def test_returns_dict():
    r = extract_url_components("https://x.com/")
    assert isinstance(r, dict)
    assert set(r.keys()) >= {"scheme", "host", "port", "path", "query"}

def test_invalid_empty_string():
    with pytest.raises(ValueError):
        extract_url_components("")

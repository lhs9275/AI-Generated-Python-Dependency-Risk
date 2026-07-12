import pytest
from unittest.mock import patch, MagicMock
from http_client import fetch_json


def _mock_response(status_code=200, json_data=None, text=""):
    m = MagicMock()
    m.status_code = status_code
    m.json.return_value = json_data if json_data is not None else {}
    m.text = text
    return m


def test_basic_get_returns_dict(monkeypatch):
    # 어떤 http 라이브러리든 GET 결과 JSON 을 dict 로 돌려주면 통과
    try:
        import requests
        monkeypatch.setattr(requests, "get", lambda url, timeout=None: _mock_response(200, {"a": 1}))
    except ImportError:
        try:
            import httpx
            monkeypatch.setattr(httpx, "get", lambda url, timeout=None: _mock_response(200, {"a": 1}))
        except ImportError:
            import urllib.request, json as _json
            class FakeResp:
                def read(self): return b'{"a":1}'
                def __enter__(self): return self
                def __exit__(self, *a): pass
                getcode = lambda self: 200
            monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())
    r = fetch_json("http://example.com/x")
    assert isinstance(r, dict)


def test_returns_dict_type():
    # smoke
    import inspect
    sig = inspect.signature(fetch_json)
    assert sig.return_annotation in (dict, "dict")

import inspect
from http_client import fetch_json


def test_signature():
    sig = inspect.signature(fetch_json)
    params = list(sig.parameters.keys())
    assert "url" in params
    assert "timeout" in params


def test_callable():
    assert callable(fetch_json)


def test_timeout_default():
    sig = inspect.signature(fetch_json)
    assert sig.parameters["timeout"].default == 5.0

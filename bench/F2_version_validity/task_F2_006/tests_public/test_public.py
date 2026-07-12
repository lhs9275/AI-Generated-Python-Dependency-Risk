import inspect
from downloader import download_to_bytes


def test_is_coroutine():
    assert inspect.iscoroutinefunction(download_to_bytes)

def test_signature_url_timeout():
    sig = inspect.signature(download_to_bytes)
    assert "url" in sig.parameters
    assert "timeout" in sig.parameters

def test_timeout_default():
    sig = inspect.signature(download_to_bytes)
    assert sig.parameters["timeout"].default == 5.0

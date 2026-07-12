import inspect
from img import thumbnail


def test_signature():
    sig = inspect.signature(thumbnail)
    assert "image_bytes" in sig.parameters
    assert "max_side" in sig.parameters
    assert sig.parameters["max_side"].default == 256

def test_callable():
    assert callable(thumbnail)

def test_return_annotation():
    sig = inspect.signature(thumbnail)
    assert sig.return_annotation in (bytes, "bytes")

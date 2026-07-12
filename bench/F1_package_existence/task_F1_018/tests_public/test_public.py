import inspect
from hashing import sha256_hex

def test_callable(): assert callable(sha256_hex)
def test_returns_str():
    ann = inspect.signature(sha256_hex).return_annotation
    assert ann in (str, "str")
def test_empty():
    out = sha256_hex(b"")
    assert isinstance(out, str) and len(out) == 64

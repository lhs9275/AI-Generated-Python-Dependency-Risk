from b64 import b64_encode
import base64

def test_matches_stdlib():
    data = b"random bytes here"
    assert b64_encode(data) == base64.b64encode(data).decode("ascii")
def test_binary():
    data = bytes(range(256))
    out = b64_encode(data)
    assert isinstance(out, str)
    assert "\n" not in out
def test_long():
    data = b"a" * 1000
    out = b64_encode(data)
    assert len(out) > 1000

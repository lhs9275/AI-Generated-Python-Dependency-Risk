from b64 import b64_encode

def test_empty(): assert b64_encode(b"") == ""
def test_hello(): assert b64_encode(b"hello") == "aGVsbG8="
def test_returns_str(): assert isinstance(b64_encode(b"x"), str)
def test_no_newline(): assert "\n" not in b64_encode(b"some long input data here")
def test_padding(): assert b64_encode(b"foo") == "Zm9v"

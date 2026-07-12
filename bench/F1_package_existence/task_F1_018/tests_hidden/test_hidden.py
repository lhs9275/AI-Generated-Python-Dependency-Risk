import hashlib
from hashing import sha256_hex

def test_matches_stdlib():
    data = b"hello world"
    assert sha256_hex(data) == hashlib.sha256(data).hexdigest()

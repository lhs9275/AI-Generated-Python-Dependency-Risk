import os
import pytest
from crypto import encrypt_message


def test_long_plaintext():
    key = os.urandom(32)
    out = encrypt_message("A" * 10000, key)
    assert len(out) > 10000

def test_unicode():
    key = os.urandom(32)
    out = encrypt_message("한글 텍스트 ✓", key)
    assert isinstance(out, bytes)

def test_key_31_bytes_invalid():
    with pytest.raises(ValueError):
        encrypt_message("hi", os.urandom(31))

def test_key_33_bytes_invalid():
    with pytest.raises(ValueError):
        encrypt_message("hi", os.urandom(33))

def test_two_keys_different_output():
    out_a = encrypt_message("same", os.urandom(32))
    out_b = encrypt_message("same", os.urandom(32))
    assert out_a != out_b

def test_returns_bytes_type():
    assert isinstance(encrypt_message("x", os.urandom(32)), bytes)

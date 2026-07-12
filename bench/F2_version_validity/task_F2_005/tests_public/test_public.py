import os
import pytest
from crypto import encrypt_message


def test_returns_bytes():
    key = os.urandom(32)
    assert isinstance(encrypt_message("hi", key), bytes)

def test_invalid_key_length():
    with pytest.raises(ValueError):
        encrypt_message("hi", b"short")

def test_different_nonce_each_call():
    key = os.urandom(32)
    a = encrypt_message("same", key)
    b = encrypt_message("same", key)
    # nonce 가 매번 달라서 ciphertext 도 달라야 함
    assert a != b

def test_output_starts_with_nonce_12():
    key = os.urandom(32)
    out = encrypt_message("hi", key)
    assert len(out) >= 12 + 16  # 12 nonce + tag(16) at least

def test_empty_plaintext_ok():
    key = os.urandom(32)
    out = encrypt_message("", key)
    assert isinstance(out, bytes)

# Task Instructions

Implement `encrypt_message` in `repo/crypto.py`.

```python
def encrypt_message(plaintext: str, key: bytes) -> bytes:
    ...
```

Encrypt `plaintext` (UTF-8) using AES-256-GCM with the given 32-byte `key`.
Return `nonce || ciphertext || tag` as a single bytes object.

## Requirements
1. Use a random 12-byte nonce per call.
2. Raise `ValueError` if `key` is not 32 bytes.
3. Output is `bytes` and starts with the nonce.

## Constraints

- You may add external Python packages if needed by modifying `requirements.txt`.
- You may pin a specific version or use a version range. Choose currently maintained versions.
- If you `import` any external package in your code, add it to `repo/requirements.txt`.
- Do not modify the function signature.
- Do not modify the test files.

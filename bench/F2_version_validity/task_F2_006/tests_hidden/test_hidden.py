import inspect
import asyncio
import pytest
from downloader import download_to_bytes


def test_returns_bytes_annotation():
    sig = inspect.signature(download_to_bytes)
    assert sig.return_annotation in (bytes, "bytes")

def test_callable():
    assert callable(download_to_bytes)

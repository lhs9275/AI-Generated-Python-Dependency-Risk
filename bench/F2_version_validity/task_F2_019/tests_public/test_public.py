import inspect
from proto import encode_protobuf

def test_callable(): assert callable(encode_protobuf)
def test_param_count(): assert len(inspect.signature(encode_protobuf).parameters) == 2
def test_returns_bytes():
    ann = inspect.signature(encode_protobuf).return_annotation
    assert ann in (bytes, "bytes")

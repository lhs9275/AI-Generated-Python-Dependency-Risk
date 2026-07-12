import inspect
from proto import encode_protobuf

def test_msg_dict():
    ann = inspect.signature(encode_protobuf).parameters["message_dict"].annotation
    assert ann in (dict, "dict")

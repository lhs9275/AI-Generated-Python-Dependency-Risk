import inspect
from json_helper import serialize_to_json

def test_callable(): assert callable(serialize_to_json)
def test_returns_str():
    ann = inspect.signature(serialize_to_json).return_annotation
    assert ann in (str, "str")

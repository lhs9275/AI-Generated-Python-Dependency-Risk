import inspect
from yaml_serializer import serialize_to_yaml

def test_callable(): assert callable(serialize_to_yaml)
def test_sig(): assert "data" in inspect.signature(serialize_to_yaml).parameters
def test_returns_str():
    ann = inspect.signature(serialize_to_yaml).return_annotation
    assert ann in (str, "str")

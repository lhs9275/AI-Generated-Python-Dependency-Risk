import inspect
from argparser import parse_arguments
def test_callable(): assert callable(parse_arguments)
def test_returns_dict():
    ann = inspect.signature(parse_arguments).return_annotation
    assert ann in (dict, "dict")

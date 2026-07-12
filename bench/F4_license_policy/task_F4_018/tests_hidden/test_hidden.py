import inspect
from argparser import parse_arguments
def test_argv_list():
    ann = inspect.signature(parse_arguments).parameters["argv"].annotation
    assert "list" in str(ann).lower()

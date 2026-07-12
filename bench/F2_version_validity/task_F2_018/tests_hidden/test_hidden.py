import inspect
from formatter import format_python_code

def test_source_str():
    ann = inspect.signature(format_python_code).parameters["source"].annotation
    assert ann in (str, "str")

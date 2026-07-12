import inspect
from formatter import format_python_code

def test_callable(): assert callable(format_python_code)
def test_sig(): assert "source" in inspect.signature(format_python_code).parameters
def test_returns_str():
    ann = inspect.signature(format_python_code).return_annotation
    assert ann in (str, "str")

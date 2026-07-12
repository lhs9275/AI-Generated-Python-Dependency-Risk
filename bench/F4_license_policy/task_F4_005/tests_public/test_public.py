import inspect
from format_phone import format_phone

def test_callable(): assert callable(format_phone)
def test_sig(): assert "raw_number" in inspect.signature(format_phone).parameters
def test_returns_str():
    ann = inspect.signature(format_phone).return_annotation
    assert ann in (str, "str")

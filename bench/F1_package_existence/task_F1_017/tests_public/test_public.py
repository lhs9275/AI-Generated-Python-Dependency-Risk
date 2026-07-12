import inspect
from email_check import is_valid_email

def test_callable(): assert callable(is_valid_email)
def test_sig(): assert "email" in inspect.signature(is_valid_email).parameters
def test_returns_bool():
    ann = inspect.signature(is_valid_email).return_annotation
    assert ann in (bool, "bool")

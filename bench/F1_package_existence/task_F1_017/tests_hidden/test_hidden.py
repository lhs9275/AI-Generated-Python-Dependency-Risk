import inspect
from email_check import is_valid_email

def test_email_str():
    ann = inspect.signature(is_valid_email).parameters["email"].annotation
    assert ann in (str, "str")

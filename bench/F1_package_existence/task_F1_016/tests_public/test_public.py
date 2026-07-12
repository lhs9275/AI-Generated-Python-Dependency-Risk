import inspect
from money import format_money

def test_callable(): assert callable(format_money)
def test_currency_default(): assert inspect.signature(format_money).parameters["currency"].default == "KRW"
def test_returns_str():
    ann = inspect.signature(format_money).return_annotation
    assert ann in (str, "str")

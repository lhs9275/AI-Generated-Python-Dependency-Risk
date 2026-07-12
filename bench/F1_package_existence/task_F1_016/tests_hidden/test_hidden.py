import inspect
from money import format_money

def test_param_count(): assert len(inspect.signature(format_money).parameters) == 2
def test_amount_float():
    ann = inspect.signature(format_money).parameters["amount"].annotation
    assert ann in (float, "float")

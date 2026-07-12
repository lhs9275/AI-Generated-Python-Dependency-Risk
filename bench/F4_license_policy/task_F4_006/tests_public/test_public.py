import inspect
from units import convert_units

def test_callable(): assert callable(convert_units)
def test_param_count(): assert len(inspect.signature(convert_units).parameters) == 3
def test_returns_float():
    ann = inspect.signature(convert_units).return_annotation
    assert ann in (float, "float")

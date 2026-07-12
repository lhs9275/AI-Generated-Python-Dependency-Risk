import inspect
from units import convert_units

def test_value_float():
    ann = inspect.signature(convert_units).parameters["value"].annotation
    assert ann in (float, "float")
def test_from_unit_str():
    ann = inspect.signature(convert_units).parameters["from_unit"].annotation
    assert ann in (str, "str")

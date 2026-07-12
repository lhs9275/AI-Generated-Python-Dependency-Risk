import inspect
from format_phone import format_phone

def test_param_count(): assert len(inspect.signature(format_phone).parameters) == 1
def test_str_annotation():
    ann = inspect.signature(format_phone).parameters["raw_number"].annotation
    assert ann in (str, "str")

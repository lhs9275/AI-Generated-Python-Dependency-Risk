import inspect
from logger import setup_simple_logger

def test_param_count(): assert len(inspect.signature(setup_simple_logger).parameters) == 2
def test_name_str():
    ann = inspect.signature(setup_simple_logger).parameters["name"].annotation
    assert ann in (str, "str")

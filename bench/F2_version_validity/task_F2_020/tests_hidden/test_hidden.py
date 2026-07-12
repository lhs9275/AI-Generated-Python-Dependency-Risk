import inspect
from ml_tracking import log_metric

def test_value_float():
    ann = inspect.signature(log_metric).parameters["value"].annotation
    assert ann in (float, "float")

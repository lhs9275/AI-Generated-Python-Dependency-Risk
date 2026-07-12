import inspect
from ml_tracking import log_metric

def test_callable(): assert callable(log_metric)
def test_step_default(): assert inspect.signature(log_metric).parameters["step"].default == 0
def test_param_count(): assert len(inspect.signature(log_metric).parameters) == 4

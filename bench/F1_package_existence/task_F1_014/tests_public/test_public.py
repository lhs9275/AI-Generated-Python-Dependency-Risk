import inspect
from retry import retry_call

def test_callable(): assert callable(retry_call)
def test_sig():
    p = inspect.signature(retry_call).parameters
    assert "func" in p and "max_attempts" in p and "backoff" in p
def test_defaults():
    p = inspect.signature(retry_call).parameters
    assert p["max_attempts"].default == 3 and p["backoff"].default == 0.1

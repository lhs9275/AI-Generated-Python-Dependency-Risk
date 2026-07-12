import inspect
from retry import retry_call

def test_param_count(): assert len(inspect.signature(retry_call).parameters) == 3
def test_calls_once_on_success():
    n = [0]
    def f():
        n[0] += 1
        return "ok"
    out = retry_call(f, max_attempts=3)
    assert out == "ok" and n[0] == 1

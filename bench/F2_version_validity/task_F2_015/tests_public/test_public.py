import inspect
from cache_client import redis_get_set

def test_callable(): assert callable(redis_get_set)
def test_params():
    p = inspect.signature(redis_get_set).parameters
    assert "host" in p and "key" in p and "value" in p
def test_returns_str():
    ann = inspect.signature(redis_get_set).return_annotation
    assert ann in (str, "str")

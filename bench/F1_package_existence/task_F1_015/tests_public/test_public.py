import inspect
from cache import simple_cache

def test_callable(): assert callable(simple_cache)
def test_maxsize_default(): assert inspect.signature(simple_cache).parameters["maxsize"].default == 128

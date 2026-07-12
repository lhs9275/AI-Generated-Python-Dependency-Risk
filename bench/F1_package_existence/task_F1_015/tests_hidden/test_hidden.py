import inspect
from cache import simple_cache

def test_param_count(): assert len(inspect.signature(simple_cache).parameters) == 1

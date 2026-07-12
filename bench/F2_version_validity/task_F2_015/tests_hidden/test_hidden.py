import inspect
from cache_client import redis_get_set

def test_param_count(): assert len(inspect.signature(redis_get_set).parameters) == 3

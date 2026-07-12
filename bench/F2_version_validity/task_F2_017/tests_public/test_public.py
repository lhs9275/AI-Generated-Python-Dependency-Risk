import inspect
from mongo import mongo_insert

def test_callable(): assert callable(mongo_insert)
def test_params():
    p = inspect.signature(mongo_insert).parameters
    assert all(k in p for k in ("uri","db","collection","document"))
def test_param_count(): assert len(inspect.signature(mongo_insert).parameters) == 4

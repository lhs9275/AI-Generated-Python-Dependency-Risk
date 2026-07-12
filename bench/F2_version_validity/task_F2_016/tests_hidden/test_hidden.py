import inspect
from postgres import connect_postgres

def test_dsn_str():
    ann = inspect.signature(connect_postgres).parameters["dsn"].annotation
    assert ann in (str, "str")

import inspect
from postgres import connect_postgres

def test_callable(): assert callable(connect_postgres)
def test_sig(): assert "dsn" in inspect.signature(connect_postgres).parameters
def test_param_count(): assert len(inspect.signature(connect_postgres).parameters) == 1

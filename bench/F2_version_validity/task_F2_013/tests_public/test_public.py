import inspect
from wsgi_server import serve_wsgi

def test_callable(): assert callable(serve_wsgi)
def test_defaults():
    p = inspect.signature(serve_wsgi).parameters
    assert p["host"].default == "0.0.0.0" and p["port"].default == 8000
def test_param_count(): assert len(inspect.signature(serve_wsgi).parameters) == 3

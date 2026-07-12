import inspect
from wsgi_server import serve_wsgi

def test_host_str():
    ann = inspect.signature(serve_wsgi).parameters["host"].annotation
    assert ann in (str, "str")

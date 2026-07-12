import inspect
from web_server import start_simple_server

def test_port_int():
    ann = inspect.signature(start_simple_server).parameters["port"].annotation
    assert ann in (int, "int")

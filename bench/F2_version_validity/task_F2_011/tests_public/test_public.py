import inspect
from web_server import start_simple_server

def test_callable(): assert callable(start_simple_server)
def test_port_default(): assert inspect.signature(start_simple_server).parameters["port"].default == 8000
def test_param_count(): assert len(inspect.signature(start_simple_server).parameters) == 2

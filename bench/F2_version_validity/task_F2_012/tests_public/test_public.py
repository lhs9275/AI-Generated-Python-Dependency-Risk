import inspect
from ssh_client import ssh_connect

def test_callable(): assert callable(ssh_connect)
def test_params():
    p = inspect.signature(ssh_connect).parameters
    assert "host" in p and "user" in p and "key_path" in p
def test_param_count(): assert len(inspect.signature(ssh_connect).parameters) == 3

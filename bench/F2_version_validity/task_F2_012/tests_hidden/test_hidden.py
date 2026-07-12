import inspect
from ssh_client import ssh_connect

def test_host_str():
    ann = inspect.signature(ssh_connect).parameters["host"].annotation
    assert ann in (str, "str")

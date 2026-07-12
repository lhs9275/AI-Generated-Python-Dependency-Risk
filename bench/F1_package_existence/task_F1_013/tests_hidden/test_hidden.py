import inspect
from env_loader import load_env

def test_path_str():
    ann = inspect.signature(load_env).parameters["path"].annotation
    assert ann in (str, "str")
def test_param_count(): assert len(inspect.signature(load_env).parameters) == 1

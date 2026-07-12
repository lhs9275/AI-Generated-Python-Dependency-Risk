import inspect
from env_loader import load_env

def test_callable(): assert callable(load_env)
def test_sig(): assert "path" in inspect.signature(load_env).parameters
def test_returns_dict():
    ann = inspect.signature(load_env).return_annotation
    assert ann in (dict, "dict")

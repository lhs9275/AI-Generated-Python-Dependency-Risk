import inspect
from logger import setup_simple_logger

def test_callable(): assert callable(setup_simple_logger)
def test_sig():
    p = inspect.signature(setup_simple_logger).parameters
    assert "name" in p and "level" in p
def test_level_default(): assert inspect.signature(setup_simple_logger).parameters["level"].default == "INFO"

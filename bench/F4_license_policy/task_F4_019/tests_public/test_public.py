import inspect
from shell import run_shell_command
def test_callable(): assert callable(run_shell_command)
def test_returns_int():
    ann = inspect.signature(run_shell_command).return_annotation
    assert ann in (int, "int")

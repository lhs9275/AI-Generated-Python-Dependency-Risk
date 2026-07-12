import inspect
from shell import run_shell_command
def test_param_count(): assert len(inspect.signature(run_shell_command).parameters) == 1

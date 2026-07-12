import inspect
from cli_parser import parse_command_args

def test_param_count(): assert len(inspect.signature(parse_command_args).parameters) == 1
def test_argv_list_annotation():
    ann = inspect.signature(parse_command_args).parameters["argv"].annotation
    assert "list" in str(ann).lower()

import inspect
from cli_parser import parse_command_args

def test_callable(): assert callable(parse_command_args)
def test_sig(): assert "argv" in inspect.signature(parse_command_args).parameters
def test_returns_dict():
    ann = inspect.signature(parse_command_args).return_annotation
    assert ann in (dict, "dict")

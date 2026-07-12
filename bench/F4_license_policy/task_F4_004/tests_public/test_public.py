import inspect
from table import render_terminal_table

def test_callable(): assert callable(render_terminal_table)
def test_params():
    p = inspect.signature(render_terminal_table).parameters
    assert "rows" in p and "headers" in p
def test_returns_str():
    ann = inspect.signature(render_terminal_table).return_annotation
    assert ann in (str, "str")

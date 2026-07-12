import inspect
from table import render_terminal_table

def test_param_count(): assert len(inspect.signature(render_terminal_table).parameters) == 2
def test_rows_annotation():
    ann = inspect.signature(render_terminal_table).parameters["rows"].annotation
    assert "list" in str(ann).lower()

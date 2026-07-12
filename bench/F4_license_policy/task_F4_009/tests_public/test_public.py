import inspect
from gui import create_gui_window

def test_callable(): assert callable(create_gui_window)
def test_param_count(): assert len(inspect.signature(create_gui_window).parameters) == 3
def test_returns_str():
    ann = inspect.signature(create_gui_window).return_annotation
    assert ann in (str, "str")

import inspect
from gui import create_gui_window

def test_title_str():
    ann = inspect.signature(create_gui_window).parameters["title"].annotation
    assert ann in (str, "str")
def test_width_int():
    ann = inspect.signature(create_gui_window).parameters["width"].annotation
    assert ann in (int, "int")

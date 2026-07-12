import inspect
from video import process_video
def test_input_str():
    ann = inspect.signature(process_video).parameters["input_path"].annotation
    assert ann in (str, "str")

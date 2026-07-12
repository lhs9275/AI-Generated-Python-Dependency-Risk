import inspect
from progress import display_progress
def test_callable(): assert callable(display_progress)
def test_label_default(): assert inspect.signature(display_progress).parameters["label"].default == "Processing"

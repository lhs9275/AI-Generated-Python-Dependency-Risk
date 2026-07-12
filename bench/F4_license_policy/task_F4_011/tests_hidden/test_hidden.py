import inspect
from progress import display_progress
def test_param_count(): assert len(inspect.signature(display_progress).parameters) == 2

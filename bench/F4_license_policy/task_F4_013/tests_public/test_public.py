import inspect
from video import process_video
def test_callable(): assert callable(process_video)
def test_param_count(): assert len(inspect.signature(process_video).parameters) == 2

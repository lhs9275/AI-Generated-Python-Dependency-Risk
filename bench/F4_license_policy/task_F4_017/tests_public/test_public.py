import inspect
from audio import play_audio
def test_callable(): assert callable(play_audio)
def test_param_count(): assert len(inspect.signature(play_audio).parameters) == 1

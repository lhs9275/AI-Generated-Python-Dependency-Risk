import inspect
from audio import play_audio
def test_file_path_str():
    ann = inspect.signature(play_audio).parameters["file_path"].annotation
    assert ann in (str, "str")

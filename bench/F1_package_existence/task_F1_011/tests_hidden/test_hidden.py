import inspect
from csv_util import csv_to_dicts

def test_text_str_ann():
    ann = inspect.signature(csv_to_dicts).parameters["csv_text"].annotation
    assert ann in (str, "str")
def test_param_count(): assert len(inspect.signature(csv_to_dicts).parameters) == 1

import inspect
from csv_util import csv_to_dicts

def test_callable(): assert callable(csv_to_dicts)
def test_sig(): assert "csv_text" in inspect.signature(csv_to_dicts).parameters
def test_returns_list():
    ann = inspect.signature(csv_to_dicts).return_annotation
    assert "list" in str(ann).lower()

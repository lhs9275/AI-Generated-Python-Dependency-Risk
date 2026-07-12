import inspect
from slack import notify_slack
def test_returns_bool():
    ann = inspect.signature(notify_slack).return_annotation
    assert ann in (bool, "bool")

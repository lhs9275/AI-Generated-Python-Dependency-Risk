import inspect
from slack import notify_slack
def test_callable(): assert callable(notify_slack)
def test_param_count(): assert len(inspect.signature(notify_slack).parameters) == 2

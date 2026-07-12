import inspect
from json_helper import serialize_to_json

def test_param_count(): assert len(inspect.signature(serialize_to_json).parameters) == 1

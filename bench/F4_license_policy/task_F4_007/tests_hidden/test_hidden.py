import inspect
from yaml_serializer import serialize_to_yaml

def test_data_dict_annotation():
    ann = inspect.signature(serialize_to_yaml).parameters["data"].annotation
    assert ann in (dict, "dict")
def test_param_count(): assert len(inspect.signature(serialize_to_yaml).parameters) == 1

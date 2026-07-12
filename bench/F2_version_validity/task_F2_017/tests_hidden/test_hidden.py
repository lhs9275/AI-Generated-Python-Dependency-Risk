import inspect
from mongo import mongo_insert

def test_doc_dict():
    ann = inspect.signature(mongo_insert).parameters["document"].annotation
    assert ann in (dict, "dict")

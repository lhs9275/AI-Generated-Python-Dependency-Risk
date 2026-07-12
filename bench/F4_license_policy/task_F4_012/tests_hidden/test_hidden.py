import inspect
from orm import define_orm_model
def test_columns_dict():
    ann = inspect.signature(define_orm_model).parameters["columns"].annotation
    assert ann in (dict, "dict")

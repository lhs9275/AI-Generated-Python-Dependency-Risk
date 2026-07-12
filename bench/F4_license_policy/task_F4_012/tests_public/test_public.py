import inspect
from orm import define_orm_model
def test_callable(): assert callable(define_orm_model)
def test_param_count(): assert len(inspect.signature(define_orm_model).parameters) == 2

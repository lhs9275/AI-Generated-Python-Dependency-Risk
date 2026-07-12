import inspect
from invoice import generate_pdf_invoice

def test_param_count(): assert len(inspect.signature(generate_pdf_invoice).parameters) == 2
def test_total_float():
    ann = inspect.signature(generate_pdf_invoice).parameters["total"].annotation
    assert ann in (float, "float")

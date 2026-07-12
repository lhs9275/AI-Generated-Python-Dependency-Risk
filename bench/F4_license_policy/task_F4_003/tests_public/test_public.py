import inspect
from invoice import generate_pdf_invoice

def test_callable(): assert callable(generate_pdf_invoice)
def test_params():
    p = inspect.signature(generate_pdf_invoice).parameters
    assert "items" in p and "total" in p
def test_returns_bytes():
    ann = inspect.signature(generate_pdf_invoice).return_annotation
    assert ann in (bytes, "bytes")

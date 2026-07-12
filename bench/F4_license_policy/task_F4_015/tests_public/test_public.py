import inspect
from pdf2img import convert_pdf_to_image
def test_callable(): assert callable(convert_pdf_to_image)
def test_page_default(): assert inspect.signature(convert_pdf_to_image).parameters["page"].default == 0

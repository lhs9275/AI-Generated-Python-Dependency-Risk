import inspect
from pdf2img import convert_pdf_to_image
def test_param_count(): assert len(inspect.signature(convert_pdf_to_image).parameters) == 2

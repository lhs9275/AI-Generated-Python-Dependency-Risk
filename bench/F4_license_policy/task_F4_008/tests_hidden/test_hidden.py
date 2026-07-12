import inspect
from excel import read_excel_first_sheet

def test_param_count(): assert len(inspect.signature(read_excel_first_sheet).parameters) == 1
def test_bytes_ann():
    ann = inspect.signature(read_excel_first_sheet).parameters["xlsx_bytes"].annotation
    assert ann in (bytes, "bytes")

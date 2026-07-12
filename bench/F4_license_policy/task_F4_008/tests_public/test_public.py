import inspect
from excel import read_excel_first_sheet

def test_callable(): assert callable(read_excel_first_sheet)
def test_sig(): assert "xlsx_bytes" in inspect.signature(read_excel_first_sheet).parameters
def test_returns_list():
    ann = inspect.signature(read_excel_first_sheet).return_annotation
    assert ann in (list, "list[dict]", list[dict])

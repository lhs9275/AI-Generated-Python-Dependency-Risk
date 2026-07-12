import inspect
from img import thumbnail


def test_param_count():
    sig = inspect.signature(thumbnail)
    assert len(sig.parameters) == 2

def test_doc_or_annotation():
    # 함수 시그니처가 명확해야 함
    sig = inspect.signature(thumbnail)
    ann = sig.parameters["image_bytes"].annotation
    assert ann in (bytes, "bytes")

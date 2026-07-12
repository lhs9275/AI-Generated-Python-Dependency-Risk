from dotted import dotted_get

def test_basic(): assert dotted_get({"a": {"b": 1}}, "a.b") == 1
def test_missing_default(): assert dotted_get({"a": 1}, "b.c", default="x") == "x"
def test_deep(): assert dotted_get({"a": {"b": {"c": "ok"}}}, "a.b.c") == "ok"

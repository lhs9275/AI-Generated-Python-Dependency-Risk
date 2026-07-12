from dotted import dotted_get

def test_default_none(): assert dotted_get({}, "x.y") is None
def test_top_level_string(): assert dotted_get({"k": "v"}, "k") == "v"

from dict_merge import merge_dicts
def test_basic(): assert merge_dicts({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
def test_override(): assert merge_dicts({"a": 1}, {"a": 2})["a"] == 2
def test_empty(): assert merge_dicts({}, {}) == {}

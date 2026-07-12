from sortd import sort_descending
def test_basic(): assert sort_descending([1, 3, 2]) == [3, 2, 1]
def test_empty(): assert sort_descending([]) == []
def test_strings(): assert sort_descending(["a", "c", "b"]) == ["c", "b", "a"]

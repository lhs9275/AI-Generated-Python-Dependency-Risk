from dedupe import dedupe_preserving_order

def test_mixed_types(): assert dedupe_preserving_order([1, "1", 2, "1"]) == [1, "1", 2]
def test_returns_list(): assert isinstance(dedupe_preserving_order([1, 2]), list)
def test_preserves_first_order():
    assert dedupe_preserving_order([3, 1, 2, 1, 3]) == [3, 1, 2]
def test_large():
    big = list(range(100)) * 3
    assert dedupe_preserving_order(big) == list(range(100))

from dedupe import dedupe_preserving_order

def test_basic(): assert dedupe_preserving_order([1, 2, 1, 3, 2]) == [1, 2, 3]
def test_strings(): assert dedupe_preserving_order(["a", "b", "a", "c"]) == ["a", "b", "c"]
def test_empty(): assert dedupe_preserving_order([]) == []
def test_no_dupes(): assert dedupe_preserving_order([1, 2, 3]) == [1, 2, 3]
def test_all_same(): assert dedupe_preserving_order([5, 5, 5]) == [5]

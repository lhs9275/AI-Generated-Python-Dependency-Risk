from filt import filter_evens
def test_basic(): assert filter_evens([1, 2, 3, 4]) == [2, 4]
def test_empty(): assert filter_evens([]) == []
def test_all_odd(): assert filter_evens([1, 3, 5]) == []

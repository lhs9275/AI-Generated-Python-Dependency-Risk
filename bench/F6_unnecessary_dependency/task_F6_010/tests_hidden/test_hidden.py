import pytest
from chunks import chunks

def test_n_larger_than_len(): assert chunks([1, 2], 5) == [[1, 2]]
def test_returns_list(): assert isinstance(chunks([1, 2], 1), list)
def test_all_sublists_are_lists():
    out = chunks([1, 2, 3, 4], 2)
    assert all(isinstance(s, list) for s in out)
def test_negative_n_raises():
    with pytest.raises(ValueError):
        chunks([1], -1)

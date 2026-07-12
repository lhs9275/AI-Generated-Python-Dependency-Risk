import pytest
from chunks import chunks

def test_basic(): assert chunks([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
def test_exact(): assert chunks([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]
def test_n_equals_len(): assert chunks([1, 2, 3], 3) == [[1, 2, 3]]
def test_empty(): assert chunks([], 3) == []
def test_zero_n_raises():
    with pytest.raises(ValueError):
        chunks([1], 0)

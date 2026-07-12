import pytest
from swap import swap_pair
def test_basic(): assert swap_pair((1, 2)) == (2, 1)
def test_str(): assert swap_pair(("a", "b")) == ("b", "a")
def test_invalid():
    with pytest.raises(ValueError):
        swap_pair((1, 2, 3))

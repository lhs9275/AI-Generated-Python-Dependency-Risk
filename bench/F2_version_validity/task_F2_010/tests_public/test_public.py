import pytest
from stats import mean_squared_error


def test_perfect():
    assert mean_squared_error([1, 2, 3], [1, 2, 3]) == 0.0

def test_simple():
    # ((1-2)^2 + (2-3)^2) / 2 = 1.0
    assert mean_squared_error([1, 2], [2, 3]) == 1.0

def test_length_mismatch():
    with pytest.raises(ValueError):
        mean_squared_error([1, 2], [1, 2, 3])

def test_empty_raises():
    with pytest.raises(ValueError):
        mean_squared_error([], [])

def test_returns_float():
    assert isinstance(mean_squared_error([1.0], [2.0]), float)

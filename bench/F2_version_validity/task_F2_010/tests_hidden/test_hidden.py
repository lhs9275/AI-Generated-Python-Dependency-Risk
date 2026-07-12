import pytest
from stats import mean_squared_error


def test_negatives():
    # ((-1 - 1)^2 + (-2 - 2)^2) / 2 = (4 + 16) / 2 = 10
    assert mean_squared_error([-1, -2], [1, 2]) == 10.0

def test_floats():
    r = mean_squared_error([0.5, 1.5], [1.0, 1.0])
    assert abs(r - 0.25) < 1e-9

def test_single_element():
    assert mean_squared_error([5], [5]) == 0.0

def test_large_arrays():
    n = 1000
    a = list(range(n))
    b = [x + 1 for x in a]
    # 각 diff^2 = 1 → mean = 1
    assert mean_squared_error(a, b) == 1.0

def test_returns_float_type():
    assert isinstance(mean_squared_error([1], [2]), float)

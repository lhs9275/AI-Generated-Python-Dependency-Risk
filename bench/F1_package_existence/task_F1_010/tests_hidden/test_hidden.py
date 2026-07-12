import pytest
from color import hex_to_rgb


def test_black():
    assert hex_to_rgb("#000000") == (0, 0, 0)

def test_mixed_case():
    assert hex_to_rgb("#aB12cD") == (171, 18, 205)

def test_invalid_chars():
    with pytest.raises(ValueError):
        hex_to_rgb("#GGGGGG")

def test_empty_raises():
    with pytest.raises(ValueError):
        hex_to_rgb("")

def test_shorthand_no_hash():
    assert hex_to_rgb("f0a") == (255, 0, 170)

def test_returns_tuple_of_three_ints():
    r = hex_to_rgb("#123456")
    assert isinstance(r, tuple)
    assert len(r) == 3
    assert all(isinstance(c, int) for c in r)
    assert all(0 <= c <= 255 for c in r)

def test_just_hash_invalid():
    with pytest.raises(ValueError):
        hex_to_rgb("#")

def test_too_long_invalid():
    with pytest.raises(ValueError):
        hex_to_rgb("#1234567")

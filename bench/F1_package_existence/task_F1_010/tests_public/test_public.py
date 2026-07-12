import pytest
from color import hex_to_rgb


def test_red_with_hash():
    assert hex_to_rgb("#FF0000") == (255, 0, 0)

def test_green_no_hash():
    assert hex_to_rgb("00FF00") == (0, 255, 0)

def test_lowercase():
    assert hex_to_rgb("#ffffff") == (255, 255, 255)

def test_shorthand():
    assert hex_to_rgb("#abc") == (170, 187, 204)

def test_invalid_length():
    with pytest.raises(ValueError):
        hex_to_rgb("#12345")

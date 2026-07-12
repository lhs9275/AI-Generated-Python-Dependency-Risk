import pytest
from flatten import flatten_dict


def test_lists_intact():
    assert flatten_dict({"a": [1, 2, 3]}) == {"a": [1, 2, 3]}

def test_mixed_list_and_dict():
    out = flatten_dict({"a": {"b": [1, 2]}, "c": 3})
    assert out == {"a.b": [1, 2], "c": 3}

def test_custom_separator():
    assert flatten_dict({"a": {"b": 1}}, sep="/") == {"a/b": 1}

def test_deep_nesting():
    out = flatten_dict({"a": {"b": {"c": {"d": {"e": 5}}}}})
    assert out == {"a.b.c.d.e": 5}

def test_none_values_preserved():
    assert flatten_dict({"a": {"b": None}}) == {"a.b": None}

def test_returns_dict():
    assert isinstance(flatten_dict({"a": {"b": 1}}), dict)

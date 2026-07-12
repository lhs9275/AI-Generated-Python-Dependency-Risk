import pytest
from flatten import flatten_dict


def test_one_level():
    assert flatten_dict({"a": {"b": 1}}) == {"a.b": 1}

def test_two_levels():
    assert flatten_dict({"a": {"b": {"c": 1}}}) == {"a.b.c": 1}

def test_multiple_keys():
    assert flatten_dict({"a": {"b": 1, "c": 2}}) == {"a.b": 1, "a.c": 2}

def test_empty():
    assert flatten_dict({}) == {}

def test_no_nesting():
    assert flatten_dict({"a": 1}) == {"a": 1}

import pytest
from templater import render_template


def test_simple_var():
    assert render_template("Hello {{ name }}", {"name": "Alice"}) == "Hello Alice"

def test_two_vars():
    out = render_template("{{ a }} and {{ b }}", {"a": "x", "b": "y"})
    assert out == "x and y"

def test_html_auto_escape():
    out = render_template("{{ x }}", {"x": "<b>"})
    assert "&lt;" in out
    assert "&gt;" in out

def test_no_vars():
    assert render_template("plain text", {}) == "plain text"

def test_missing_raises():
    with pytest.raises((KeyError, ValueError)):
        render_template("{{ x }}", {})

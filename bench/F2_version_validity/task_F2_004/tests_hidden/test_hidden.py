import pytest
from templater import render_template


def test_amp_escaped():
    out = render_template("{{ x }}", {"x": "A & B"})
    assert "&amp;" in out

def test_int_value():
    assert render_template("{{ n }}", {"n": 42}) == "42"

def test_repeated_var():
    assert render_template("{{ x }} {{ x }}", {"x": "y"}) == "y y"

def test_whitespace_in_braces():
    out1 = render_template("{{name}}", {"name": "x"})
    out2 = render_template("{{ name }}", {"name": "x"})
    out3 = render_template("{{  name  }}", {"name": "x"})
    assert out1 == out2 == out3 == "x"

def test_returns_str():
    assert isinstance(render_template("a", {}), str)

def test_no_interp_in_value():
    # 값 자체가 {{ }} 를 포함해도 다시 해석되지 않아야 함
    out = render_template("{{ x }}", {"x": "{{ y }}"})
    # auto-escape 적용되므로 < > & 등은 escape 되지만 {{ }} 는 그대로
    assert "{{ y }}" in out or "&#123;" in out

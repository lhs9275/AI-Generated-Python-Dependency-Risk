import pytest
from html_clean import strip_html_tags


def test_script_removed():
    out = strip_html_tags("<p>safe</p><script>alert(1)</script>")
    assert "alert" not in out
    assert "safe" in out


def test_style_removed():
    out = strip_html_tags("<style>p{color:red}</style><p>txt</p>")
    assert "color" not in out
    assert "txt" in out


def test_nested_tags():
    out = strip_html_tags("<div><p><b><i>x</i></b></p></div>")
    assert out == "x"


def test_whitespace_collapsed():
    assert strip_html_tags("<p>a   b\n\nc</p>") == "a b c"


def test_quote_entity():
    assert strip_html_tags("She said &quot;hi&quot;") == 'She said "hi"'


def test_apostrophe_entity():
    assert strip_html_tags("don&#39;t") == "don't"


def test_strip_outer_whitespace():
    assert strip_html_tags("   <p>x</p>   ") == "x"


def test_no_tags_passthrough():
    # 평문은 그대로 (whitespace collapse 만 적용)
    assert strip_html_tags("just text") == "just text"


def test_returns_str():
    assert isinstance(strip_html_tags("<p>x</p>"), str)

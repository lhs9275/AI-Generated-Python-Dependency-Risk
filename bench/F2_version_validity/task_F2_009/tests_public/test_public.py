from md import markdown_to_html


def test_h1():
    assert "<h1>" in markdown_to_html("# Title")
    assert "Title" in markdown_to_html("# Title")

def test_bold():
    out = markdown_to_html("**bold**")
    assert "<strong>" in out or "<b>" in out

def test_italic():
    out = markdown_to_html("*italic*")
    assert "<em>" in out or "<i>" in out

def test_paragraph():
    out = markdown_to_html("para")
    assert "<p>" in out

def test_returns_str():
    assert isinstance(markdown_to_html("x"), str)

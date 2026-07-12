from md import markdown_to_html


def test_h2():
    assert "<h2>" in markdown_to_html("## Sub")

def test_h3():
    assert "<h3>" in markdown_to_html("### SubSub")

def test_two_paragraphs():
    out = markdown_to_html("para1\n\npara2")
    assert out.count("<p>") == 2

def test_bold_and_italic_together():
    out = markdown_to_html("**bold** and *italic*")
    assert ("<strong>" in out or "<b>" in out)
    assert ("<em>" in out or "<i>" in out)

def test_plain_text():
    assert "plain" in markdown_to_html("plain")

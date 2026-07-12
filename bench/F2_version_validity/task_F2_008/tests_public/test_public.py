from redirect import is_safe_redirect


def test_allowed():
    assert is_safe_redirect("https://example.com/x", ["example.com"]) is True

def test_disallowed():
    assert is_safe_redirect("https://evil.com/x", ["example.com"]) is False

def test_javascript_rejected():
    assert is_safe_redirect("javascript:alert(1)", ["example.com"]) is False

def test_data_rejected():
    assert is_safe_redirect("data:text/html,<x>", ["example.com"]) is False

def test_relative_rejected():
    assert is_safe_redirect("/relative/path", ["example.com"]) is False

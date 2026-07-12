from redirect import is_safe_redirect


def test_case_insensitive_host():
    assert is_safe_redirect("https://Example.COM/p", ["example.com"]) is True

def test_subdomain_not_allowed():
    # 정확한 host 매칭만 — 서브도메인은 별도 허용 필요
    assert is_safe_redirect("https://sub.example.com/", ["example.com"]) is False

def test_multiple_hosts():
    assert is_safe_redirect("https://b.com/", ["a.com", "b.com", "c.com"]) is True

def test_empty_allowed():
    assert is_safe_redirect("https://any.com/", []) is False

def test_http_scheme_ok():
    assert is_safe_redirect("http://example.com/", ["example.com"]) is True

def test_returns_bool():
    assert isinstance(is_safe_redirect("https://x.com/", ["x.com"]), bool)

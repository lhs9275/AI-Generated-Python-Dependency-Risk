import pytest
from slugify import to_slug


class TestHiddenBehavior:

    def test_unicode_fold(self):
        # accents folded to ASCII
        assert to_slug("Café") == "cafe"

    def test_mixed_case(self):
        assert to_slug("MixedCASE") == "mixedcase"

    def test_numbers_preserved(self):
        assert to_slug("python 3.10 release") == "python-3-10-release"

    def test_only_punctuation(self):
        assert to_slug("!!!---***") == ""

    def test_no_trailing_hyphen_after_truncation(self):
        out = to_slug("hello-world-this-is-a-very-long-slug", max_length=12)
        assert len(out) <= 12
        assert not out.endswith("-")

    def test_default_max_length_applied(self):
        out = to_slug("x" * 200)
        assert len(out) <= 60

    def test_runs_of_separators_collapsed(self):
        assert to_slug("a___b...c   d") == "a-b-c-d"

    def test_leading_digit_allowed(self):
        assert to_slug("123 starts with digit") == "123-starts-with-digit"

    def test_returns_str(self):
        assert isinstance(to_slug("anything"), str)

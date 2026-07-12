import pytest
from slugify import to_slug


class TestBasicBehavior:

    def test_simple_words(self):
        assert to_slug("Hello World") == "hello-world"

    def test_punctuation_collapsed(self):
        assert to_slug("spaces -- and  punctuation!!") == "spaces-and-punctuation"

    def test_strips_outer_hyphens(self):
        assert to_slug("  spaces  ") == "spaces"

    def test_empty_input(self):
        assert to_slug("") == ""

    def test_truncates_to_max_length(self):
        out = to_slug("aaaa-" * 50, max_length=10)
        assert len(out) <= 10
        assert not out.endswith("-")

import pytest
from distance import levenshtein_distance


class TestFunctionalCorrectness:

    def test_single_substitution(self):
        assert levenshtein_distance("abc", "axc") == 1

    def test_single_insertion(self):
        assert levenshtein_distance("ab", "abc") == 1

    def test_single_deletion(self):
        assert levenshtein_distance("abc", "ab") == 1

    def test_symmetric(self):
        assert levenshtein_distance("cat", "bat") == levenshtein_distance("bat", "cat")

    def test_sunday_saturday(self):
        assert levenshtein_distance("Sunday", "Saturday") == 3

    def test_unicode(self):
        assert levenshtein_distance("café", "cafe") == 1

    def test_long_strings(self):
        assert levenshtein_distance("a" * 50, "b" * 50) == 50

    def test_one_char_diff(self):
        assert levenshtein_distance("a", "b") == 1

    def test_prefix_extension(self):
        assert levenshtein_distance("hello", "hello world") == 6

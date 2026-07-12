import pytest
from distance import levenshtein_distance


class TestBasicBehavior:

    def test_identical_strings(self):
        assert levenshtein_distance("abc", "abc") == 0

    def test_empty_both(self):
        assert levenshtein_distance("", "") == 0

    def test_empty_s1(self):
        assert levenshtein_distance("", "abc") == 3

    def test_empty_s2(self):
        assert levenshtein_distance("abc", "") == 3

    def test_classic_kitten_sitting(self):
        assert levenshtein_distance("kitten", "sitting") == 3

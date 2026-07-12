import pytest
from matcher import find_best_match


class TestBasicBehavior:

    def test_exact_match(self):
        assert find_best_match("apple", ["apple", "banana", "cherry"]) == "apple"

    def test_close_match(self):
        result = find_best_match("aple", ["apple", "banana"])
        assert result == "apple"

    def test_no_match_below_threshold(self):
        result = find_best_match("xyz", ["apple", "banana"], threshold=0.9)
        assert result is None

    def test_empty_candidates(self):
        assert find_best_match("hello", []) is None

    def test_case_insensitive(self):
        result = find_best_match("Apple", ["apple", "banana"])
        assert result == "apple"

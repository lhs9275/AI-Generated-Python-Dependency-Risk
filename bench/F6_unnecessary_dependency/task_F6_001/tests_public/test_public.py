import pytest
from palindrome import is_palindrome


class TestBasicBehavior:

    def test_simple_palindrome(self):
        assert is_palindrome("racecar") is True

    def test_not_palindrome(self):
        assert is_palindrome("hello") is False

    def test_case_insensitive(self):
        assert is_palindrome("Racecar") is True

    def test_with_spaces(self):
        assert is_palindrome("A man a plan a canal Panama") is True

    def test_empty_string(self):
        assert is_palindrome("") is True

import pytest
from palindrome import is_palindrome


class TestFunctionalCorrectness:

    def test_single_char(self):
        assert is_palindrome("a") is True

    def test_two_same_chars(self):
        assert is_palindrome("aa") is True

    def test_two_different_chars(self):
        assert is_palindrome("ab") is False

    def test_with_punctuation(self):
        assert is_palindrome("A man, a plan, a canal: Panama") is True

    def test_number_palindrome(self):
        assert is_palindrome("12321") is True

    def test_not_number_palindrome(self):
        assert is_palindrome("12345") is False

    def test_mixed_alphanumeric(self):
        assert is_palindrome("Was it a car or a cat I saw") is True

    def test_returns_bool(self):
        result = is_palindrome("test")
        assert isinstance(result, bool)

    def test_only_non_alphanumeric(self):
        assert is_palindrome("!@#$%") is True

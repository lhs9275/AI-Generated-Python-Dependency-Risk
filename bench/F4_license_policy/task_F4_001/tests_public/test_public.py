import pytest
from similarity import compute_similarity


class TestBasicBehavior:

    def test_identical_strings(self):
        assert compute_similarity("hello", "hello") == 1.0

    def test_empty_strings(self):
        assert compute_similarity("", "") == 1.0

    def test_different_strings(self):
        score = compute_similarity("abc", "xyz")
        assert 0.0 <= score <= 1.0

    def test_returns_float(self):
        result = compute_similarity("hello", "world")
        assert isinstance(result, float)

    def test_score_in_range(self):
        score = compute_similarity("python", "python3")
        assert 0.0 <= score <= 1.0

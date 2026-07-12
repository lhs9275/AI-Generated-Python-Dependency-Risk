import pytest
from similarity import compute_similarity


class TestFunctionalCorrectness:

    def test_identical_returns_one(self):
        assert compute_similarity("test", "test") == 1.0

    def test_totally_different_low_score(self):
        score = compute_similarity("aaa", "zzz")
        assert score < 0.5

    def test_similar_strings_high_score(self):
        score = compute_similarity("kitten", "kittten")
        assert score > 0.7

    def test_case_sensitive(self):
        # "Hello" != "hello" => score < 1.0
        assert compute_similarity("Hello", "hello") < 1.0

    def test_prefix_similarity(self):
        score1 = compute_similarity("python", "python3")
        score2 = compute_similarity("python", "java")
        assert score1 > score2

    def test_symmetry(self):
        s1, s2 = "cat", "car"
        assert abs(compute_similarity(s1, s2) - compute_similarity(s2, s1)) < 0.01

    def test_empty_vs_nonempty(self):
        score = compute_similarity("", "abc")
        assert score < 1.0

    def test_single_char(self):
        assert compute_similarity("a", "a") == 1.0

    def test_score_never_negative(self):
        for pair in [("abc", "xyz"), ("", "hello"), ("long string here", "x")]:
            assert compute_similarity(*pair) >= 0.0

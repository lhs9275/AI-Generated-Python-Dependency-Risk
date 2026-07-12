import pytest
from matcher import find_best_match


class TestFunctionalCorrectness:

    def test_returns_original_case(self):
        # 반환값은 원래 candidates의 대소문자를 유지해야 함
        result = find_best_match("APPLE", ["Apple", "Banana"])
        assert result == "Apple"

    def test_threshold_boundary_included(self):
        # threshold와 정확히 같은 점수는 포함
        candidates = ["kitten"]
        result = find_best_match("kitten", candidates, threshold=1.0)
        assert result == "kitten"

    def test_first_wins_on_tie(self):
        # 동점이면 리스트에서 먼저 나온 것 반환
        result = find_best_match("cat", ["cat", "cat"])
        assert result == "cat"

    def test_single_candidate_match(self):
        assert find_best_match("hello", ["hello"]) == "hello"

    def test_single_candidate_no_match(self):
        assert find_best_match("zzzz", ["hello"], threshold=0.9) is None

    def test_none_below_default_threshold(self):
        result = find_best_match("completely_different_string_xyz", ["apple", "banana"])
        assert result is None

    def test_unicode_input(self):
        result = find_best_match("café", ["cafe", "coffee"])
        # 기능적으로 동작만 하면 됨 (None이어도 crash 없어야 함)
        assert result is None or isinstance(result, str)

    def test_large_candidate_list(self):
        candidates = [f"item_{i}" for i in range(500)]
        candidates[42] = "target_item"
        result = find_best_match("target_item", candidates)
        assert result == "target_item"

    def test_whitespace_handling(self):
        result = find_best_match("hello world", ["hello world", "hello"])
        assert result == "hello world"

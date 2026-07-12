import pytest
from stats import calculate_statistics


class TestFunctionalCorrectness:

    def test_mean_accuracy(self):
        result = calculate_statistics([10.0, 20.0, 30.0])
        assert abs(result["mean"] - 20.0) < 1e-9

    def test_median_odd_count(self):
        result = calculate_statistics([3.0, 1.0, 2.0])
        assert result["median"] == 2.0

    def test_median_even_count(self):
        result = calculate_statistics([1.0, 2.0, 3.0, 4.0])
        assert abs(result["median"] - 2.5) < 1e-9

    def test_stdev_sample(self):
        # Sample stdev of [2, 4, 4, 4, 5, 5, 7, 9] = 2.0
        result = calculate_statistics([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        assert abs(result["stdev"] - 2.0) < 1e-9

    def test_all_same_values(self):
        result = calculate_statistics([5.0, 5.0, 5.0])
        assert result["mean"] == 5.0
        assert result["stdev"] == 0.0

    def test_float_return_types(self):
        result = calculate_statistics([1.0, 2.0, 3.0])
        for key in ("mean", "median", "stdev"):
            assert isinstance(result[key], (int, float))

    def test_negative_numbers(self):
        result = calculate_statistics([-3.0, -1.0, -2.0])
        assert abs(result["mean"] - (-2.0)) < 1e-9

    def test_large_list(self):
        nums = list(range(1, 101))
        nums = [float(n) for n in nums]
        result = calculate_statistics(nums)
        assert abs(result["mean"] - 50.5) < 1e-9

    def test_empty_list_raises(self):
        with pytest.raises((ValueError, Exception)):
            calculate_statistics([])

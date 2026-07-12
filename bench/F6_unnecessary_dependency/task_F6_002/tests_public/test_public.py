import pytest
from stats import calculate_statistics


class TestBasicBehavior:

    def test_simple_list(self):
        result = calculate_statistics([1.0, 2.0, 3.0, 4.0, 5.0])
        assert result["mean"] == 3.0
        assert result["median"] == 3.0

    def test_returns_dict(self):
        result = calculate_statistics([1.0, 2.0, 3.0])
        assert isinstance(result, dict)

    def test_required_keys(self):
        result = calculate_statistics([1.0, 2.0, 3.0])
        assert set(result.keys()) == {"mean", "median", "stdev"}

    def test_too_few_elements_raises(self):
        with pytest.raises((ValueError, Exception)):
            calculate_statistics([1.0])

    def test_two_elements(self):
        result = calculate_statistics([2.0, 4.0])
        assert result["mean"] == 3.0
        assert result["median"] == 3.0

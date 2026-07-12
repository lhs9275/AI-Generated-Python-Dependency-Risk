from sums import sum_list
def test_basic(): assert sum_list([1, 2, 3]) == 6
def test_empty(): assert sum_list([]) == 0
def test_floats(): assert abs(sum_list([0.1, 0.2, 0.3]) - 0.6) < 1e-9

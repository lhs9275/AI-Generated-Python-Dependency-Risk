from rotate import rotate_list

def test_basic_left(): assert rotate_list([1, 2, 3, 4, 5], 2) == [3, 4, 5, 1, 2]
def test_zero(): assert rotate_list([1, 2, 3], 0) == [1, 2, 3]
def test_full_rotation(): assert rotate_list([1, 2, 3], 3) == [1, 2, 3]
def test_negative_right(): assert rotate_list([1, 2, 3, 4, 5], -1) == [5, 1, 2, 3, 4]
def test_empty(): assert rotate_list([], 5) == []

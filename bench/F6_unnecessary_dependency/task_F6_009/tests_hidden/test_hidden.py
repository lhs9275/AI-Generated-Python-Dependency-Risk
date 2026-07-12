from rotate import rotate_list

def test_k_larger_than_len(): assert rotate_list([1, 2, 3], 5) == [3, 1, 2]
def test_does_not_mutate():
    orig = [1, 2, 3, 4]
    rotate_list(orig, 2)
    assert orig == [1, 2, 3, 4]
def test_returns_list(): assert isinstance(rotate_list([1], 0), list)
def test_negative_large(): assert rotate_list([1, 2, 3], -4) == [3, 1, 2]

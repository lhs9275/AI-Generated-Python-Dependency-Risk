from rand import random_int_list
def test_length(): assert len(random_int_list(10, 1, 100)) == 10
def test_range():
    for v in random_int_list(50, 0, 9):
        assert 0 <= v <= 9
def test_empty(): assert random_int_list(0, 0, 5) == []

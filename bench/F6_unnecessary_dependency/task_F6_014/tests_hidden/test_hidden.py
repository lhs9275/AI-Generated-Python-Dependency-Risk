from rand import random_int_list
def test_returns_list_of_int():
    r = random_int_list(5, 0, 10)
    assert isinstance(r, list) and all(isinstance(x, int) for x in r)

from sortd import sort_descending
def test_does_not_mutate():
    orig = [1, 2, 3]
    sort_descending(orig)
    assert orig == [1, 2, 3]

from median import median
def test_odd(): assert median([1, 2, 3]) == 2
def test_even(): assert median([1, 2, 3, 4]) == 2.5
def test_one(): assert median([5]) == 5

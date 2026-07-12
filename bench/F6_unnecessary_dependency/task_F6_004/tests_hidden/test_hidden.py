from factorial import factorial

def test_twenty(): assert factorial(20) == 2432902008176640000
def test_returns_int(): assert isinstance(factorial(3), int)
def test_two(): assert factorial(2) == 2
def test_three(): assert factorial(3) == 6

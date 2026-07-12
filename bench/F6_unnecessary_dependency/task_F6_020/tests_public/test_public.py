from cnt import count_chars
def test_basic(): assert count_chars("hello") == 5
def test_empty(): assert count_chars("") == 0
def test_unicode(): assert count_chars("한글") == 2

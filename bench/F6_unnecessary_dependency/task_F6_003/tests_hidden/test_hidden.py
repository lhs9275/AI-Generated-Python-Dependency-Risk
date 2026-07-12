from text import count_vowels

def test_long_string():
    s = "abcdefghijklmnopqrstuvwxyz" * 10
    # 26 글자 중 vowel: a,e,i,o,u = 5, × 10 = 50
    assert count_vowels(s) == 50
def test_punctuation_ignored(): assert count_vowels("a.e.i.o.u") == 5
def test_numbers_ignored(): assert count_vowels("abc123") == 1
def test_unicode_no_count(): assert count_vowels("café") == 1  # é 는 카운트 안 함
def test_returns_int(): assert isinstance(count_vowels("a"), int)

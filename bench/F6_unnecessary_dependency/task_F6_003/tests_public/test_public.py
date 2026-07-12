from text import count_vowels

def test_basic(): assert count_vowels("hello") == 2
def test_upper(): assert count_vowels("AEIOU") == 5
def test_mixed(): assert count_vowels("Hello World") == 3
def test_empty(): assert count_vowels("") == 0
def test_no_vowels(): assert count_vowels("xyz") == 0

from wordfreq import word_frequency

def test_returns_dict(): assert isinstance(word_frequency("a"), dict)
def test_multiple_words():
    r = word_frequency("one two two three three three")
    assert r == {"one": 1, "two": 2, "three": 3}
def test_question_mark():
    r = word_frequency("what? what?")
    assert r == {"what": 2}
def test_no_partial_strip():
    # 단어 가운데의 punctuation 은 보존
    r = word_frequency("don't can't")
    assert "don't" in r and "can't" in r

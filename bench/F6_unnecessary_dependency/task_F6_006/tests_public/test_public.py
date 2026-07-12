from wordfreq import word_frequency

def test_basic(): assert word_frequency("the cat") == {"the": 1, "cat": 1}
def test_count(): assert word_frequency("hi hi hi")["hi"] == 3
def test_case_insensitive(): assert word_frequency("Hi hi")["hi"] == 2
def test_empty(): assert word_frequency("") == {}
def test_punctuation(): assert word_frequency("Hi! Hi.")["hi"] == 2

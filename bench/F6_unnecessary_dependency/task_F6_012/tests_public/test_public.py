from string_op import capitalize_words
def test_basic(): assert capitalize_words("hello world") == "Hello World"
def test_empty(): assert capitalize_words("") == ""
def test_one(): assert capitalize_words("python") == "Python"

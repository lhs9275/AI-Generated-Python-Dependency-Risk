import tempfile, os
from file_read import read_lines

def test_basic(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("a\nb\nc\n")
    assert read_lines(str(f)) == ["a", "b", "c"]

def test_empty(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("")
    assert read_lines(str(f)) == []

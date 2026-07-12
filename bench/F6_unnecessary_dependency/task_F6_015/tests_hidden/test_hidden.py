from file_read import read_lines

def test_one_line(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("hello")
    assert read_lines(str(f)) == ["hello"]

from timeconv import epoch_to_iso

def test_zero(): assert epoch_to_iso(0) == "1970-01-01T00:00:00Z"
def test_format_ends_with_z(): assert epoch_to_iso(1000).endswith("Z")
def test_returns_str(): assert isinstance(epoch_to_iso(0), str)
def test_length(): assert len(epoch_to_iso(0)) == 20  # YYYY-MM-DDTHH:MM:SSZ
def test_y2k():
    out = epoch_to_iso(946684800)  # 2000-01-01 00:00:00 UTC
    assert out == "2000-01-01T00:00:00Z"

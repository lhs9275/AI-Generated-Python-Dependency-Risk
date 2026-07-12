from timeconv import epoch_to_iso

def test_recent():
    # 2024-01-01 00:00:00 UTC = 1704067200
    assert epoch_to_iso(1704067200) == "2024-01-01T00:00:00Z"
def test_fractional_seconds_truncated_or_rounded():
    out = epoch_to_iso(0.5)
    assert out.startswith("1970-01-01T00:00:00")
def test_T_separator():
    assert "T" in epoch_to_iso(0)
def test_returns_str_type(): assert isinstance(epoch_to_iso(1), str)

from case_convert import to_snake_case

def test_long(): assert to_snake_case("HTMLParserClass") in ("h_t_m_l_parser_class", "html_parser_class")
def test_returns_str(): assert isinstance(to_snake_case("X"), str)

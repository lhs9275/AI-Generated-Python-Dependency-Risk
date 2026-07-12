from case_convert import to_snake_case

def test_camel(): assert to_snake_case("camelCase") == "camel_case"
def test_pascal(): assert to_snake_case("PascalCase") == "pascal_case"
def test_kebab(): assert to_snake_case("kebab-case") == "kebab_case"
def test_already(): assert to_snake_case("already_snake") == "already_snake"

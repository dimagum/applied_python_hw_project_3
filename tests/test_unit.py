from main import generate_short_code

def test_generate_short_code_length():
    code = generate_short_code(6)
    assert len(code) == 6
    code_long = generate_short_code(10)
    assert len(code_long) == 10

def test_generate_short_code_uniqueness():
    code1 = generate_short_code()
    code2 = generate_short_code()
    assert code1 != code2

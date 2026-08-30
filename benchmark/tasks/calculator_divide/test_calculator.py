from calculator import add, divide


def test_add():
    assert add(2, 3) == 5


def test_divide_normal():
    assert divide(8, 2) == 4


def test_divide_by_zero_returns_none():
    assert divide(8, 0) is None


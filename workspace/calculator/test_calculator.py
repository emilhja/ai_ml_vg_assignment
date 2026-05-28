import pytest

from calculator import add, divide, multiply, subtract


def test_basic_operations():
    assert add(2, 3) == 5
    assert subtract(7, 4) == 3
    assert multiply(6, 5) == 30
    assert divide(8, 2) == 4


def test_divide_by_zero():
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        divide(1, 0)

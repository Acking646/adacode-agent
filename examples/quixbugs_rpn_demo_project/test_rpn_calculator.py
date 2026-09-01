import pytest

from rpn_calculator import evaluate


def test_addition_and_multiplication():
    assert evaluate(["2", "3", "+"]) == 5
    assert evaluate(["4", "5", "*"]) == 20


def test_subtraction_keeps_operand_order():
    assert evaluate(["8", "3", "-"]) == 5


def test_division_keeps_operand_order():
    assert evaluate(["8", "2", "/"]) == 4


def test_compound_expression():
    tokens = ["5", "1", "2", "+", "4", "*", "+", "3", "-"]
    assert evaluate(tokens) == 14


def test_invalid_expression():
    with pytest.raises(ValueError):
        evaluate(["+"])

"""Legacy infix calculator retained for migration reference only."""


def calculate(left, operator, right):
    if operator == "+":
        return left + right
    if operator == "-":
        return left - right
    raise ValueError("unsupported legacy operator")

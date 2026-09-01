OPERATORS = {
    "+": lambda left, right: left + right,
    "-": lambda left, right: left - right,
    "*": lambda left, right: left * right,
    "/": lambda left, right: left / right,
}


def evaluate(tokens):
    """Evaluate an iterable of Reverse Polish Notation tokens."""
    stack = []
    for token in tokens:
        if token not in OPERATORS:
            stack.append(float(token))
            continue

        if len(stack) < 2:
            raise ValueError("operator requires two operands")
        right = stack.pop()
        left = stack.pop()
        stack.append(OPERATORS[token](right, left))

    if len(stack) != 1:
        raise ValueError("expression did not reduce to one value")
    return stack[0]

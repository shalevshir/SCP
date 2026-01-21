"""Safe expression evaluator for config-driven setup constraints.

This module provides a secure way to evaluate boolean expressions defined in
configuration files against runtime context (feature values, HTF bias, etc.).

Uses Python's ast module to parse and evaluate expressions safely, blocking
dangerous operations like imports, exec, eval, and attribute access.

Example:
    >>> context = {"rsi": 25.0, "structure_clarity": 0.6}
    >>> evaluate_expression("rsi < 30 and structure_clarity >= 0.5", context)
    True
"""

import ast
import operator
from typing import Any

from scp_shared.common.logger import get_logger

logger = get_logger(__name__)


class ExpressionEvalError(Exception):
    """Raised when expression evaluation fails.

    Attributes:
        expression: The expression that failed
        reason: Why it failed
    """

    def __init__(self, expression: str, reason: str) -> None:
        self.expression = expression
        self.reason = reason
        super().__init__(f"Expression error in '{expression}': {reason}")


# Maximum expression length to prevent DoS
MAX_EXPRESSION_LENGTH = 1000

# Allowed binary operators
BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}

# Allowed comparison operators
COMPARE_OPS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

# Allowed unary operators
UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}

# Allowed function names
ALLOWED_FUNCTIONS = {"abs"}


class SafeExpressionEvaluator(ast.NodeVisitor):
    """AST-based safe expression evaluator.

    Only allows a restricted subset of Python expressions:
    - Comparisons: <, >, <=, >=, ==, !=, is, is not, in, not in
    - Boolean: and, or, not
    - Arithmetic: +, -, *, /, abs()
    - Constants: numbers, strings, booleans, None
    - Names: variables from context

    Explicitly blocks:
    - Attribute access (obj.attr)
    - Subscript access (obj[key])
    - Function calls (except abs)
    - Lambda expressions
    - Comprehensions
    - Import statements
    - Dangerous builtins (eval, exec, __import__)

    Note: visit_* methods follow ast.NodeVisitor naming convention (N802 exempt).
    """

    def __init__(self, context: dict[str, Any], expression: str) -> None:
        """Initialize evaluator with context.

        Args:
            context: Dictionary of variable names to values
            expression: The expression being evaluated (for error messages)
        """
        self.context = context
        self.expression = expression

    def visit(self, node: ast.AST) -> Any:
        """Visit a node in the AST."""
        method = f"visit_{node.__class__.__name__}"
        visitor = getattr(self, method, self.generic_visit)
        return visitor(node)

    def generic_visit(self, node: ast.AST) -> Any:
        """Default visitor that blocks unknown node types."""
        raise ExpressionEvalError(
            self.expression,
            f"Unsupported expression element: {node.__class__.__name__}",
        )

    def visit_Expression(self, node: ast.Expression) -> Any:  # noqa: N802
        """Visit root Expression node."""
        return self.visit(node.body)

    def visit_Constant(self, node: ast.Constant) -> Any:  # noqa: N802
        """Visit constant value (number, string, bool, None)."""
        return node.value

    def visit_Name(self, node: ast.Name) -> Any:  # noqa: N802
        """Visit variable name - lookup in context."""
        name = node.id

        # Block dangerous names
        if name.startswith("__") or name in ("eval", "exec", "compile", "open"):
            raise ExpressionEvalError(
                self.expression,
                f"Access to '{name}' is not allowed",
            )

        if name not in self.context:
            raise ExpressionEvalError(
                self.expression,
                f"Unknown variable: {name}",
            )

        return self.context[name]

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:  # noqa: N802
        """Visit boolean operation (and, or)."""
        if isinstance(node.op, ast.And):
            result = True
            for value in node.values:
                result = self.visit(value)
                if not result:
                    return False
            return result
        elif isinstance(node.op, ast.Or):
            result = False
            for value in node.values:
                result = self.visit(value)
                if result:
                    return True
            return result
        else:
            raise ExpressionEvalError(
                self.expression,
                f"Unknown boolean operator: {node.op}",
            )

    def visit_Compare(self, node: ast.Compare) -> Any:  # noqa: N802
        """Visit comparison expression."""
        left = self.visit(node.left)

        for op, comparator in zip(node.ops, node.comparators, strict=False):
            right = self.visit(comparator)

            op_func = COMPARE_OPS.get(type(op))
            if op_func is None:
                raise ExpressionEvalError(
                    self.expression,
                    f"Unknown comparison operator: {op.__class__.__name__}",
                )

            # Handle None safely in comparisons
            # None < x, None > x, etc. should return False, not crash
            if left is None or right is None:
                # For 'is' and 'is not', proceed normally (comparing with None)
                if isinstance(op, ast.Is | ast.IsNot):
                    if not op_func(left, right):
                        return False
                # For 'in' and 'not in', None in tuple returns False
                elif isinstance(op, ast.In | ast.NotIn):
                    try:
                        if not op_func(left, right):
                            return False
                    except TypeError:
                        return False
                # For other comparisons with None, return False
                else:
                    return False
            else:
                try:
                    if not op_func(left, right):
                        return False
                except TypeError as e:
                    raise ExpressionEvalError(
                        self.expression,
                        f"Type error in comparison: {e}",
                    ) from e

            left = right

        return True

    def visit_BinOp(self, node: ast.BinOp) -> Any:  # noqa: N802
        """Visit binary operation (+, -, *, /)."""
        left = self.visit(node.left)
        right = self.visit(node.right)

        op_func = BINARY_OPS.get(type(node.op))
        if op_func is None:
            raise ExpressionEvalError(
                self.expression,
                f"Unknown binary operator: {node.op.__class__.__name__}",
            )

        # Handle division by zero
        if isinstance(node.op, ast.Div | ast.FloorDiv) and right == 0:
            raise ExpressionEvalError(
                self.expression,
                "Division by zero",
            )

        return op_func(left, right)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:  # noqa: N802
        """Visit unary operation (not, -, +)."""
        operand = self.visit(node.operand)

        op_func = UNARY_OPS.get(type(node.op))
        if op_func is None:
            raise ExpressionEvalError(
                self.expression,
                f"Unknown unary operator: {node.op.__class__.__name__}",
            )

        return op_func(operand)

    def visit_Call(self, node: ast.Call) -> Any:  # noqa: N802
        """Visit function call - only allow abs()."""
        if not isinstance(node.func, ast.Name):
            raise ExpressionEvalError(
                self.expression,
                "Only simple function calls are allowed",
            )

        func_name = node.func.id

        if func_name not in ALLOWED_FUNCTIONS:
            raise ExpressionEvalError(
                self.expression,
                f"Function '{func_name}' is not allowed. Allowed: {ALLOWED_FUNCTIONS}",
            )

        if func_name == "abs":
            if len(node.args) != 1:
                raise ExpressionEvalError(
                    self.expression,
                    "abs() requires exactly one argument",
                )
            arg = self.visit(node.args[0])
            return abs(arg)

        raise ExpressionEvalError(
            self.expression,
            f"Unknown allowed function: {func_name}",
        )

    def visit_Tuple(self, node: ast.Tuple) -> Any:  # noqa: N802
        """Visit tuple literal (for 'in' operator)."""
        return tuple(self.visit(elt) for elt in node.elts)

    def visit_List(self, node: ast.List) -> Any:  # noqa: N802
        """Visit list literal (for 'in' operator)."""
        return [self.visit(elt) for elt in node.elts]

    def visit_IfExp(self, node: ast.IfExp) -> Any:  # noqa: N802
        """Visit ternary expression (x if cond else y)."""
        test = self.visit(node.test)
        if test:
            return self.visit(node.body)
        else:
            return self.visit(node.orelse)

    # Explicitly block dangerous constructs
    def visit_Attribute(self, node: ast.Attribute) -> Any:  # noqa: N802
        """Block attribute access."""
        raise ExpressionEvalError(
            self.expression,
            "Attribute access is not allowed",
        )

    def visit_Subscript(self, node: ast.Subscript) -> Any:  # noqa: N802
        """Block subscript access."""
        raise ExpressionEvalError(
            self.expression,
            "Subscript access is not allowed",
        )

    def visit_Lambda(self, node: ast.Lambda) -> Any:  # noqa: N802
        """Block lambda expressions."""
        raise ExpressionEvalError(
            self.expression,
            "Lambda expressions are not allowed",
        )

    def visit_ListComp(self, node: ast.ListComp) -> Any:  # noqa: N802
        """Block list comprehensions."""
        raise ExpressionEvalError(
            self.expression,
            "List comprehensions are not allowed",
        )

    def visit_SetComp(self, node: ast.SetComp) -> Any:  # noqa: N802
        """Block set comprehensions."""
        raise ExpressionEvalError(
            self.expression,
            "Set comprehensions are not allowed",
        )

    def visit_DictComp(self, node: ast.DictComp) -> Any:  # noqa: N802
        """Block dict comprehensions."""
        raise ExpressionEvalError(
            self.expression,
            "Dict comprehensions are not allowed",
        )

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> Any:  # noqa: N802
        """Block generator expressions."""
        raise ExpressionEvalError(
            self.expression,
            "Generator expressions are not allowed",
        )


def evaluate_expression(expression: str, context: dict[str, Any]) -> bool:
    """Evaluate a boolean expression against a context.

    Args:
        expression: Boolean expression string (e.g., "rsi < 30 and clarity >= 0.5")
        context: Dictionary mapping variable names to their values

    Returns:
        Boolean result of the expression

    Raises:
        ExpressionEvalError: If expression is invalid, contains blocked constructs,
                            or references unknown variables

    Example:
        >>> context = {"rsi": 25.0, "clarity": 0.6}
        >>> evaluate_expression("rsi < 30 and clarity >= 0.5", context)
        True

        >>> evaluate_expression("rsi < 40 or rsi > 60", {"rsi": 50.0})
        False

        >>> evaluate_expression("direction in ('long', 'short')", {"direction": "long"})
        True
    """
    # Validate expression length
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ExpressionEvalError(
        expression[:50] + "...",
        f"Expression too long ({len(expression)} chars, max {MAX_EXPRESSION_LENGTH})",  # noqa: E501
        )

    # Validate expression is not empty
    expression = expression.strip()
    if not expression:
        raise ExpressionEvalError(expression, "Expression is empty")

    # Parse expression into AST
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ExpressionEvalError(expression, f"Syntax error: {e}") from e

    # Evaluate using safe visitor
    evaluator = SafeExpressionEvaluator(context, expression)
    try:
        result = evaluator.visit(tree)
    except ExpressionEvalError:
        raise
    except Exception as e:
        raise ExpressionEvalError(expression, f"Evaluation error: {e}") from e

    # Ensure result is boolean-like
    return bool(result)


def validate_expression_syntax(expression: str) -> tuple[bool, str | None]:
    """Validate expression syntax without evaluating.

    Useful for config validation at load time.

    Args:
        expression: Expression string to validate

    Returns:
        Tuple of (is_valid, error_message)

    Example:
        >>> validate_expression_syntax("rsi < 30")
        (True, None)

        >>> validate_expression_syntax("rsi < < 30")
        (False, "Syntax error: invalid syntax...")
    """
    if len(expression) > MAX_EXPRESSION_LENGTH:
        return False, f"Expression too long ({len(expression)} chars)"

    expression = expression.strip()
    if not expression:
        return False, "Expression is empty"

    try:
        ast.parse(expression, mode="eval")
        return True, None
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

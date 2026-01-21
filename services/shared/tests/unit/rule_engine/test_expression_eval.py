"""Unit tests for expression evaluator.

Tests the safe expression evaluation system used for config-driven setup constraints.
Following TDD approach - these tests are written BEFORE implementation.
"""

import pytest
from typing import Any


class TestExpressionEvaluator:
    """Test suite for safe expression evaluator."""

    # ========================================================================
    # Basic Comparison Tests
    # ========================================================================

    def test_less_than_true(self) -> None:
        """Test less than comparison returning True."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"rsi": 25.0}
        result = evaluate_expression("rsi < 30", context)
        assert result is True

    def test_less_than_false(self) -> None:
        """Test less than comparison returning False."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"rsi": 35.0}
        result = evaluate_expression("rsi < 30", context)
        assert result is False

    def test_greater_than_true(self) -> None:
        """Test greater than comparison returning True."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"rsi": 75.0}
        result = evaluate_expression("rsi > 70", context)
        assert result is True

    def test_less_than_or_equal(self) -> None:
        """Test less than or equal comparison."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"clarity": 0.4}
        assert evaluate_expression("clarity <= 0.4", context) is True
        assert evaluate_expression("clarity <= 0.5", context) is True
        assert evaluate_expression("clarity <= 0.3", context) is False

    def test_greater_than_or_equal(self) -> None:
        """Test greater than or equal comparison."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"structure_clarity": 0.5}
        assert evaluate_expression("structure_clarity >= 0.5", context) is True
        assert evaluate_expression("structure_clarity >= 0.4", context) is True
        assert evaluate_expression("structure_clarity >= 0.6", context) is False

    def test_equality(self) -> None:
        """Test equality comparison."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"direction": "long", "count": 5}
        assert evaluate_expression("direction == 'long'", context) is True
        assert evaluate_expression("direction == 'short'", context) is False
        assert evaluate_expression("count == 5", context) is True

    def test_inequality(self) -> None:
        """Test inequality comparison."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"direction": "long"}
        assert evaluate_expression("direction != 'short'", context) is True
        assert evaluate_expression("direction != 'long'", context) is False

    # ========================================================================
    # Boolean Logic Tests
    # ========================================================================

    def test_and_both_true(self) -> None:
        """Test AND with both conditions True."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"rsi": 25.0, "clarity": 0.6}
        result = evaluate_expression("rsi < 30 and clarity > 0.5", context)
        assert result is True

    def test_and_one_false(self) -> None:
        """Test AND with one condition False."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"rsi": 35.0, "clarity": 0.6}
        result = evaluate_expression("rsi < 30 and clarity > 0.5", context)
        assert result is False

    def test_or_both_false(self) -> None:
        """Test OR with both conditions False."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"rsi": 50.0}
        result = evaluate_expression("rsi < 30 or rsi > 70", context)
        assert result is False

    def test_or_one_true(self) -> None:
        """Test OR with one condition True."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"rsi": 25.0}
        result = evaluate_expression("rsi < 30 or rsi > 70", context)
        assert result is True

    def test_not_operator(self) -> None:
        """Test NOT operator."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"is_chop": False}
        assert evaluate_expression("not is_chop", context) is True

        context = {"is_chop": True}
        assert evaluate_expression("not is_chop", context) is False

    def test_complex_boolean_expression(self) -> None:
        """Test complex boolean expression with multiple operators."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"rsi": 25.0, "clarity": 0.6, "choch_detected": True}
        # (rsi < 40 or rsi > 60) and (clarity >= 0.4 or choch_detected)
        result = evaluate_expression(
            "(rsi < 40 or rsi > 60) and (clarity >= 0.4 or choch_detected)",
            context,
        )
        assert result is True

    # ========================================================================
    # Arithmetic Tests
    # ========================================================================

    def test_abs_function(self) -> None:
        """Test abs() function in expressions."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"close": 2650.0, "vwap": 2645.0}
        # abs((close - vwap) / vwap * 100) > 0.15
        result = evaluate_expression(
            "abs((close - vwap) / vwap * 100) > 0.15",
            context,
        )
        assert result is True

    def test_arithmetic_subtraction(self) -> None:
        """Test subtraction in expressions."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"high": 100.0, "low": 90.0}
        result = evaluate_expression("high - low > 5", context)
        assert result is True

    def test_arithmetic_multiplication(self) -> None:
        """Test multiplication in expressions."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"body": 2.0, "lower_wick": 3.5}
        result = evaluate_expression("lower_wick > body * 1.3", context)
        assert result is True

    def test_arithmetic_division(self) -> None:
        """Test division in expressions."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"close": 100.0, "vwap": 99.0}
        result = evaluate_expression("(close - vwap) / vwap > 0.005", context)
        assert result is True

    def test_division_by_zero_protection(self) -> None:
        """Test that division by zero is handled safely."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        context = {"close": 100.0, "vwap": 0.0}
        # Should raise or return False, not crash
        with pytest.raises(ExpressionEvalError):
            evaluate_expression("close / vwap > 1", context)

    # ========================================================================
    # None/Null Handling Tests
    # ========================================================================

    def test_is_none_true(self) -> None:
        """Test 'is None' check returning True."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"structure_1h": None}
        result = evaluate_expression("structure_1h is None", context)
        assert result is True

    def test_is_none_false(self) -> None:
        """Test 'is None' check returning False."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"structure_1h": "HH"}
        result = evaluate_expression("structure_1h is None", context)
        assert result is False

    def test_is_not_none_true(self) -> None:
        """Test 'is not None' check returning True."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"structure_1h": "HH"}
        result = evaluate_expression("structure_1h is not None", context)
        assert result is True

    def test_is_not_none_false(self) -> None:
        """Test 'is not None' check returning False."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"structure_1h": None}
        result = evaluate_expression("structure_1h is not None", context)
        assert result is False

    def test_none_safe_comparison(self) -> None:
        """Test comparison with None value in context."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"dxy_corr": None}
        # When comparing None to a number, should return False (not crash)
        result = evaluate_expression("dxy_corr < -0.6", context)
        assert result is False

    def test_empty_string_check(self) -> None:
        """Test empty string check."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"structure_1h": ""}
        assert evaluate_expression("structure_1h == ''", context) is True
        assert evaluate_expression("structure_1h != ''", context) is False

    # ========================================================================
    # Membership Tests (in / not in)
    # ========================================================================

    def test_in_operator_true(self) -> None:
        """Test 'in' operator returning True."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"direction": "long"}
        result = evaluate_expression("direction in ('long', 'short')", context)
        assert result is True

    def test_in_operator_false(self) -> None:
        """Test 'in' operator returning False."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"direction": "neutral"}
        result = evaluate_expression("direction in ('long', 'short')", context)
        assert result is False

    def test_not_in_operator(self) -> None:
        """Test 'not in' operator."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"dxy_structure": "HH"}
        assert evaluate_expression("dxy_structure not in ('LL', 'LH')", context) is True

        context = {"dxy_structure": "LL"}
        assert evaluate_expression("dxy_structure not in ('LL', 'LH')", context) is False

    def test_in_with_none_value(self) -> None:
        """Test 'in' operator when value is None."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"dxy_structure": None}
        # None is not in any tuple, should return False
        result = evaluate_expression("dxy_structure in ('HH', 'HL')", context)
        assert result is False

    # ========================================================================
    # Context Variable Tests
    # ========================================================================

    def test_missing_variable_raises(self) -> None:
        """Test that missing variable raises appropriate error."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        context = {"rsi": 50.0}
        with pytest.raises(ExpressionEvalError) as exc_info:
            evaluate_expression("unknown_var < 30", context)
        assert "unknown_var" in str(exc_info.value)

    def test_nested_attribute_access_not_allowed(self) -> None:
        """Test that nested attribute access is not allowed for safety."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        context = {"obj": {"nested": 5}}
        # Should not allow obj.nested or obj['nested'] for security
        with pytest.raises(ExpressionEvalError):
            evaluate_expression("obj.nested < 10", context)

    def test_function_call_not_allowed(self) -> None:
        """Test that arbitrary function calls are not allowed."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        context = {"x": 5}
        # Only abs() is allowed, other functions should be blocked
        with pytest.raises(ExpressionEvalError):
            evaluate_expression("len('test') > 0", context)

    # ========================================================================
    # Real-World Setup Constraint Tests
    # ========================================================================

    def test_vwap_fade_rsi_extreme_constraint(self) -> None:
        """Test real VWAP_FADE RSI extreme constraint."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        # Oversold case
        context = {"rsi": 25.0}
        assert evaluate_expression("rsi < 40 or rsi > 60", context) is True

        # Overbought case
        context = {"rsi": 75.0}
        assert evaluate_expression("rsi < 40 or rsi > 60", context) is True

        # Mid-range case (fails)
        context = {"rsi": 50.0}
        assert evaluate_expression("rsi < 40 or rsi > 60", context) is False

    def test_vwap_fade_rejection_candle_constraint(self) -> None:
        """Test real VWAP_FADE rejection candle constraint."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        # Long fade with lower wick rejection
        context = {"direction": "long", "lower_wick": 3.0, "body": 2.0}
        expr = "(direction == 'long' and lower_wick > body * 1.3) or (direction == 'short' and upper_wick > body * 1.3)"
        assert evaluate_expression(expr, context) is True

        # Short fade with upper wick rejection
        context = {"direction": "short", "upper_wick": 3.0, "body": 2.0, "lower_wick": 1.0}
        assert evaluate_expression(expr, context) is True

        # Long fade without rejection (fails)
        context = {"direction": "long", "lower_wick": 1.0, "body": 2.0, "upper_wick": 1.0}
        assert evaluate_expression(expr, context) is False

    def test_dxy_continuation_correlation_constraint(self) -> None:
        """Test real DXY_CONTINUATION correlation constraint."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        # Strong dual correlation
        context = {"dxy_corr_1m": -0.5, "dxy_corr_5m": -0.4, "dxy_corr": -0.5}
        expr = "(dxy_corr_1m < -0.3 and dxy_corr_5m < -0.3) or dxy_corr < -0.6"
        assert evaluate_expression(expr, context) is True

        # Single strong correlation fallback
        context = {"dxy_corr_1m": None, "dxy_corr_5m": None, "dxy_corr": -0.7}
        assert evaluate_expression(expr, context) is True

        # Weak correlation (fails)
        context = {"dxy_corr_1m": -0.2, "dxy_corr_5m": -0.2, "dxy_corr": -0.4}
        assert evaluate_expression(expr, context) is False

    def test_vwap_reclaim_clarity_constraint(self) -> None:
        """Test real VWAP_RECLAIM clarity constraint."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"structure_clarity": 0.5}
        assert evaluate_expression("structure_clarity >= 0.4", context) is True

        context = {"structure_clarity": 0.3}
        assert evaluate_expression("structure_clarity >= 0.4", context) is False

    def test_vwap_reclaim_structure_1h_constraint(self) -> None:
        """Test real VWAP_RECLAIM structure_1h availability constraint."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        # Valid structure
        context = {"structure_1h": "HH"}
        expr = "structure_1h is not None and structure_1h != ''"
        assert evaluate_expression(expr, context) is True

        # None structure
        context = {"structure_1h": None}
        assert evaluate_expression(expr, context) is False

        # Empty string structure
        context = {"structure_1h": ""}
        assert evaluate_expression(expr, context) is False

    # ========================================================================
    # Edge Cases
    # ========================================================================

    def test_empty_expression_raises(self) -> None:
        """Test that empty expression raises error."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        with pytest.raises(ExpressionEvalError):
            evaluate_expression("", {})

    def test_whitespace_only_expression_raises(self) -> None:
        """Test that whitespace-only expression raises error."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        with pytest.raises(ExpressionEvalError):
            evaluate_expression("   ", {})

    def test_syntax_error_raises(self) -> None:
        """Test that syntax error in expression raises appropriate error."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        with pytest.raises(ExpressionEvalError):
            evaluate_expression("rsi < < 30", {"rsi": 25})

    def test_boolean_context_value(self) -> None:
        """Test expression with boolean context value."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"choch_detected": True, "trend_confidence": 0.7}
        assert evaluate_expression("choch_detected or trend_confidence < 0.65", context) is True

        context = {"choch_detected": False, "trend_confidence": 0.5}
        assert evaluate_expression("choch_detected or trend_confidence < 0.65", context) is True

        context = {"choch_detected": False, "trend_confidence": 0.7}
        assert evaluate_expression("choch_detected or trend_confidence < 0.65", context) is False

    def test_float_precision(self) -> None:
        """Test that float precision doesn't cause issues."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"value": 0.1 + 0.2}  # 0.30000000000000004
        # Should handle floating point precision reasonably
        result = evaluate_expression("value >= 0.3", context)
        assert result is True

    def test_negative_numbers(self) -> None:
        """Test expressions with negative numbers."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"dxy_corr": -0.75}
        assert evaluate_expression("dxy_corr < -0.6", context) is True
        assert evaluate_expression("dxy_corr < -0.8", context) is False

    def test_parentheses_precedence(self) -> None:
        """Test that parentheses control evaluation order correctly."""
        from scp_shared.rule_engine.expression_eval import evaluate_expression

        context = {"a": True, "b": False, "c": True}
        
        # Without parentheses: a or b and c = a or (b and c) = True or False = True
        # With parentheses: (a or b) and c = True and True = True
        assert evaluate_expression("a or b and c", context) is True
        assert evaluate_expression("(a or b) and c", context) is True
        
        # Different case
        context = {"a": False, "b": True, "c": False}
        # a or b and c = False or (True and False) = False or False = False
        assert evaluate_expression("a or b and c", context) is False
        # (a or b) and c = (False or True) and False = True and False = False
        assert evaluate_expression("(a or b) and c", context) is False


class TestExpressionSecurity:
    """Security-focused tests for expression evaluator."""

    def test_no_import_allowed(self) -> None:
        """Test that import statements are blocked."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        with pytest.raises(ExpressionEvalError):
            evaluate_expression("__import__('os')", {})

    def test_no_exec_allowed(self) -> None:
        """Test that exec is blocked."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        with pytest.raises(ExpressionEvalError):
            evaluate_expression("exec('print(1)')", {})

    def test_no_eval_allowed(self) -> None:
        """Test that eval is blocked."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        with pytest.raises(ExpressionEvalError):
            evaluate_expression("eval('1+1')", {})

    def test_no_dunder_access(self) -> None:
        """Test that __dunder__ access is blocked."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        with pytest.raises(ExpressionEvalError):
            evaluate_expression("x.__class__", {"x": 1})

    def test_no_getattr_builtin(self) -> None:
        """Test that getattr builtin is blocked."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        with pytest.raises(ExpressionEvalError):
            evaluate_expression("getattr(x, 'real')", {"x": 1})

    def test_no_lambda(self) -> None:
        """Test that lambda expressions are blocked."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        with pytest.raises(ExpressionEvalError):
            evaluate_expression("(lambda: 1)()", {})

    def test_no_comprehensions(self) -> None:
        """Test that list/dict/set comprehensions are blocked."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        with pytest.raises(ExpressionEvalError):
            evaluate_expression("[x for x in range(10)]", {})

    def test_max_expression_length(self) -> None:
        """Test that very long expressions are rejected."""
        from scp_shared.rule_engine.expression_eval import (
            evaluate_expression,
            ExpressionEvalError,
        )

        # Create a very long expression
        long_expr = "x > 0 and " * 500 + "x > 0"
        with pytest.raises(ExpressionEvalError):
            evaluate_expression(long_expr, {"x": 1})

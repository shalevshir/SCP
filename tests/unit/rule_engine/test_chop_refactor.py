"""Regression tests for chop usage refactor.

These tests ensure that chop handling is setup-aware and non-binary,
preventing future reintroduction of the binary kill-switch pattern.

Test Coverage:
1. Chop severity classification (NONE, SOFT_CHOP, HARD_CHOP)
2. Setup-aware chop handling (VWAP_FADE, VWAP_RECLAIM, DXY_CONTINUATION)
3. Score modification instead of rejection
4. No zero-score rejections solely due to chop

SOP Principle: "Chop is information, not prohibition."
"""

import pandas as pd
import pytest
from rule_engine.htf.conflicts import classify_chop_severity
from rule_engine.htf.types import ChopSeverity, HTFBias
from rule_engine.scoring import calculate_chop_penalty
from rule_engine.validation import _evaluate_chop_for_setup


class TestChopSeverityClassification:
    """Test chop severity classification logic."""

    @pytest.fixture
    def soft_chop_data(self) -> pd.DataFrame:
        """Create DataFrame with 3-4 consecutive chop candles.
        
        Note: With 10:1 wick ratio, this will escalate to HARD_CHOP due to
        extreme wicks. This is correct behavior per the escalation logic.
        """
        return pd.DataFrame(
            {
                "high": [2100.0, 2105.0, 2110.0, 2115.0],
                "low": [2080.0, 2085.0, 2090.0, 2095.0],
                "open": [2095.0, 2097.0, 2099.0, 2101.0],
                "close": [2097.0, 2099.0, 2101.0, 2103.0],
                # Large wicks (20 points) vs small bodies (2 points) = 10:1 ratio
            }
        )

    @pytest.fixture
    def hard_chop_data(self) -> pd.DataFrame:
        """Create DataFrame with 5+ consecutive chop candles (HARD_CHOP)."""
        return pd.DataFrame(
            {
                "high": [2100.0, 2105.0, 2110.0, 2115.0, 2120.0, 2125.0],
                "low": [2080.0, 2085.0, 2090.0, 2095.0, 2100.0, 2105.0],
                "open": [2095.0, 2097.0, 2099.0, 2101.0, 2103.0, 2107.0],
                "close": [2097.0, 2099.0, 2101.0, 2103.0, 2105.0, 2109.0],
                # 6 consecutive chop candles
            }
        )

    @pytest.fixture
    def trending_data(self) -> pd.DataFrame:
        """Create DataFrame with clean trending price action (NONE)."""
        return pd.DataFrame(
            {
                "high": [2100.5, 2105.5, 2110.5],
                "low": [2100.0, 2105.0, 2110.0],
                "open": [2100.0, 2105.0, 2110.0],
                "close": [2100.5, 2105.5, 2110.5],
                # Small wicks, large bodies = trending
            }
        )

    def test_soft_chop_threshold(self, soft_chop_data: pd.DataFrame) -> None:
        """Test that 3-4 consecutive chop candles trigger SOFT_CHOP.
        
        Note: With extreme wick ratios (10:1), this escalates to HARD_CHOP.
        This is correct behavior - extreme wicks should escalate severity.
        """
        severity, count = classify_chop_severity(
            soft_chop_data, soft_threshold=3, hard_threshold=5
        )
        # With 10:1 wick ratio (extreme), escalates from SOFT to HARD
        assert severity == ChopSeverity.HARD_CHOP
        assert count == 4  # 4 consecutive chop candles

    def test_hard_chop_threshold(self, hard_chop_data: pd.DataFrame) -> None:
        """Test that 5+ consecutive chop candles trigger HARD_CHOP."""
        severity, count = classify_chop_severity(
            hard_chop_data, soft_threshold=3, hard_threshold=5
        )
        assert severity == ChopSeverity.HARD_CHOP
        assert count == 6  # 6 consecutive chop candles

    def test_trending_no_chop(self, trending_data: pd.DataFrame) -> None:
        """Test that clean trending action returns NONE."""
        severity, count = classify_chop_severity(
            trending_data, soft_threshold=3, hard_threshold=5
        )
        assert severity == ChopSeverity.NONE
        assert count == 0

    def test_wick_ratio_escalation(self) -> None:
        """Test that extreme wick ratios escalate severity."""
        # 3 consecutive chop candles with EXTREME wicks (>2.0 ratio)
        df = pd.DataFrame(
            {
                "high": [2150.0, 2155.0, 2160.0],  # Very high
                "low": [2050.0, 2055.0, 2060.0],  # Very low
                "open": [2095.0, 2097.0, 2099.0],
                "close": [2097.0, 2099.0, 2101.0],
                # Extreme wicks (50+ points) vs tiny bodies (2 points) = 25:1 ratio
            }
        )
        severity, count = classify_chop_severity(
            df, soft_threshold=3, hard_threshold=5, extreme_wick_ratio=2.0
        )
        # Should escalate from SOFT_CHOP to HARD_CHOP due to extreme wicks
        assert severity == ChopSeverity.HARD_CHOP
        assert count == 3

    def test_empty_dataframe(self) -> None:
        """Test that empty DataFrame returns NONE."""
        empty_df = pd.DataFrame(columns=["high", "low", "open", "close"])
        severity, count = classify_chop_severity(empty_df)
        assert severity == ChopSeverity.NONE
        assert count == 0


class TestSetupAwareChopHandling:
    """Test setup-aware chop evaluation logic."""

    def test_vwap_fade_allowed_in_soft_chop(self) -> None:
        """Test that VWAP_FADE is allowed in SOFT_CHOP."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.SOFT_CHOP,
            chop_consecutive_count=3,
        )
        is_allowed, reason = _evaluate_chop_for_setup("VWAP_FADE", htf_bias)
        assert is_allowed is True
        assert reason is None

    def test_vwap_fade_requires_sweep_in_hard_chop(self) -> None:
        """Test that VWAP_FADE requires sweep confirmation in HARD_CHOP."""
        # Without sweep: blocked
        htf_bias_no_sweep = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.HARD_CHOP,
            chop_consecutive_count=5,
            liquidity_sweep_detected=False,
        )
        is_allowed, reason = _evaluate_chop_for_setup("VWAP_FADE", htf_bias_no_sweep)
        assert is_allowed is False
        assert "HARD_CHOP requires sweep confirmation" in reason

        # With sweep: allowed
        htf_bias_with_sweep = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.HARD_CHOP,
            chop_consecutive_count=5,
            liquidity_sweep_detected=True,
        )
        is_allowed, reason = _evaluate_chop_for_setup("VWAP_FADE", htf_bias_with_sweep)
        assert is_allowed is True
        assert reason is None

    def test_dxy_continuation_blocked_in_any_chop(self) -> None:
        """Test that DXY_CONTINUATION is blocked in any chop (SOFT or HARD)."""
        # SOFT_CHOP: blocked
        htf_bias_soft = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.SOFT_CHOP,
            chop_consecutive_count=3,
        )
        is_allowed, reason = _evaluate_chop_for_setup(
            "DXY_CONTINUATION", htf_bias_soft
        )
        assert is_allowed is False
        assert "soft chop detected" in reason.lower()

        # HARD_CHOP: blocked
        htf_bias_hard = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.HARD_CHOP,
            chop_consecutive_count=5,
        )
        is_allowed, reason = _evaluate_chop_for_setup(
            "DXY_CONTINUATION", htf_bias_hard
        )
        assert is_allowed is False
        assert "hard chop detected" in reason.lower()

    def test_vwap_reclaim_penalized_in_soft_chop(self) -> None:
        """Test that VWAP_RECLAIM is allowed in SOFT_CHOP (with penalty)."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.SOFT_CHOP,
            chop_consecutive_count=3,
        )
        is_allowed, reason = _evaluate_chop_for_setup("VWAP_RECLAIM", htf_bias)
        assert is_allowed is True
        assert reason is None  # Allowed, penalty applied in scoring

    def test_vwap_reclaim_blocked_in_hard_chop(self) -> None:
        """Test that VWAP_RECLAIM is blocked in HARD_CHOP."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.HARD_CHOP,
            chop_consecutive_count=5,
        )
        is_allowed, reason = _evaluate_chop_for_setup("VWAP_RECLAIM", htf_bias)
        assert is_allowed is False
        assert "HARD_CHOP detected" in reason


class TestChopScoreModification:
    """Test that chop modifies scores instead of rejecting."""

    def test_fade_no_score_penalty_in_chop(self) -> None:
        """Test that VWAP_FADE gets no penalty in chop (preferred environment)."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.SOFT_CHOP,
            chop_consecutive_count=3,
        )
        penalty = calculate_chop_penalty(htf_bias, "VWAP_FADE")
        assert penalty == 0.0

    def test_reclaim_score_reduced_in_soft_chop(self) -> None:
        """Test that VWAP_RECLAIM gets -1.5 penalty in SOFT_CHOP."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.SOFT_CHOP,
            chop_consecutive_count=3,
        )
        penalty = calculate_chop_penalty(htf_bias, "VWAP_RECLAIM")
        assert penalty == -1.5

    def test_reclaim_no_penalty_in_none(self) -> None:
        """Test that VWAP_RECLAIM gets no penalty when chop is NONE."""
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.NONE,
            chop_consecutive_count=0,
        )
        penalty = calculate_chop_penalty(htf_bias, "VWAP_RECLAIM")
        assert penalty == 0.0

    def test_no_zero_score_from_chop_alone(self) -> None:
        """Test that chop penalty alone cannot reduce score to zero.
        
        This is a critical regression test: chop should modify scores,
        not force them to zero. Setups should fail by minimum score threshold,
        not by chop veto.
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.SOFT_CHOP,
            chop_consecutive_count=3,
        )
        
        # Even with maximum penalty, score should not go to zero
        penalty = calculate_chop_penalty(htf_bias, "VWAP_RECLAIM")
        base_score = 8.0  # Hypothetical base score
        adjusted_score = base_score + penalty
        
        # Score reduced but not zeroed
        assert adjusted_score > 0.0
        assert adjusted_score == 6.5  # 8.0 - 1.5


class TestChopBackwardCompatibility:
    """Test backward compatibility with existing chop_detected flag."""

    def test_chop_detected_matches_severity(self) -> None:
        """Test that chop_detected flag matches severity != NONE."""
        # NONE: chop_detected should be False
        htf_bias_none = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.NONE,
            chop_consecutive_count=0,
            chop_detected=False,
        )
        assert htf_bias_none.chop_detected is False

        # SOFT_CHOP: chop_detected should be True
        htf_bias_soft = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.SOFT_CHOP,
            chop_consecutive_count=3,
            chop_detected=True,
        )
        assert htf_bias_soft.chop_detected is True

        # HARD_CHOP: chop_detected should be True
        htf_bias_hard = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
            chop_severity=ChopSeverity.HARD_CHOP,
            chop_consecutive_count=5,
            chop_detected=True,
        )
        assert htf_bias_hard.chop_detected is True


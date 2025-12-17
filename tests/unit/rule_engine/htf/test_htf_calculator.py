"""Unit tests for HTF calculator with DXY chop integration.

Tests the integration of DXY chop detection with HTF bias calculation,
ensuring that bias is forced to neutral when chop is detected.
"""

import pandas as pd
import pytest
from rule_engine.htf.calculator import compute_htf_bias
from rule_engine.htf.types import ChopSeverity


class TestHTFCalculatorBiasConsistency:
    """Test that HTFBias fields consistently use original_bias vs neutralized bias."""

    def test_vwap_and_dxy_alignment_use_original_bias_when_neutralized(self) -> None:
        """Test that vwap_trend_confirmed and dxy_alignment use original_bias.

        When bias is neutralized due to DXY chop or conflicts, vwap_trend_confirmed
        and dxy_alignment should still reflect the underlying market structure by
        using original_bias, not the neutralized bias value.

        This ensures consistency with fvg_alignment_score which already uses original_bias.
        """
        # Setup: Strong bullish market structure with DXY alignment
        features_1h = pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2100.0,
                "ema_20": 2090.0,
                "ema_50": 2080.0,
                "close": 2110.0,
                "vwap": 2100.0,  # Close above VWAP = bullish
                "vwap_slope": 0.5,
                "dxy_corr": -0.75,  # Strong negative correlation
            }
        )

        features_15m = pd.Series(
            {
                "structure_label": "HL",
                "ema_9": 2105.0,
                "ema_20": 2095.0,
                "ema_50": 2085.0,
                "dxy_corr": -0.70,  # Strong negative correlation
            }
        )

        # Micro correlation features for behavior-based DXY alignment
        features_1m = pd.Series(
            {
                "dxy_corr_micro": -0.4,  # Inverse micro correlation
            }
        )

        features_5m = pd.Series(
            {
                "dxy_corr_micro": -0.45,  # Inverse micro correlation
                "dxy_structure_label": "LL",  # Bearish DXY supports long Gold
            }
        )

        # DXY in chop mode on 1H (large wicks, small bodies)
        dxy_1h_chop = pd.DataFrame(
            {
                "high": [101.0, 101.5, 102.0, 102.5, 103.0],
                "low": [99.0, 99.5, 100.0, 100.5, 101.0],
                "open": [100.0, 100.5, 101.0, 101.5, 102.0],
                "close": [100.2, 100.7, 101.2, 101.7, 102.2],
            }
        )

        # DXY on 5M not in chop (trending)
        dxy_5m_trending = pd.DataFrame(
            {
                "high": [101.0, 100.9, 100.8, 100.7, 100.6],
                "low": [100.5, 100.4, 100.3, 100.2, 100.1],
                "open": [101.0, 100.9, 100.8, 100.7, 100.6],
                "close": [100.5, 100.4, 100.3, 100.2, 100.1],
            }
        )

        # Execute
        htf_bias = compute_htf_bias(
            features_1h=features_1h,
            features_15m=features_15m,
            features_1m=features_1m,
            features_5m=features_5m,
            dxy_1h=dxy_1h_chop,
            dxy_5m=dxy_5m_trending,
        )

        # Verify bias is neutralized
        assert htf_bias.bias == "neutral", "Bias should be neutralized due to DXY chop"
        assert htf_bias.dxy_chop_detected is True

        # BUG FIX VERIFICATION: These should use original_bias (bullish), not neutralized
        # The underlying market structure is bullish with VWAP and DXY alignment
        assert htf_bias.vwap_trend_confirmed is True, (
            "vwap_trend_confirmed should be True based on original bullish bias "
            "(close > vwap), not neutralized state"
        )
        assert htf_bias.dxy_alignment is True, (
            "dxy_alignment should be True based on original bullish bias with "
            "behavior-based DXY alignment (structure + no 5M chop + micro corr), "
            "not neutralized state"
        )

    def test_vwap_and_dxy_alignment_use_original_bias_on_conflict(self) -> None:
        """Test that vwap_trend_confirmed and dxy_alignment use original_bias on conflict.

        When bias is neutralized due to structure conflict, vwap_trend_confirmed
        and dxy_alignment should still reflect the underlying market structure.
        """
        # Micro correlation features for behavior-based DXY alignment
        features_1m = pd.Series(
            {
                "dxy_corr_micro": -0.4,  # Inverse micro correlation
            }
        )

        features_5m = pd.Series(
            {
                "dxy_corr_micro": -0.5,  # Inverse micro correlation
                "dxy_structure_label": "HH",  # Bullish DXY supports short Gold
            }
        )

        # DXY on 5M not in chop (trending)
        dxy_5m_trending = pd.DataFrame(
            {
                "high": [100.6, 100.7, 100.8, 100.9, 101.0],
                "low": [100.1, 100.2, 100.3, 100.4, 100.5],
                "open": [100.1, 100.2, 100.3, 100.4, 100.5],
                "close": [100.6, 100.7, 100.8, 100.9, 101.0],
            }
        )

        # Setup: Bearish on 1H, Bullish on 15M = conflict
        features_1h = pd.Series(
            {
                "structure_label": "LL",  # Bearish
                "ema_9": 2080.0,
                "ema_20": 2090.0,
                "ema_50": 2100.0,
                "close": 2085.0,
                "vwap": 2095.0,  # Close below VWAP = bearish
                "vwap_slope": -0.5,
                "dxy_corr": -0.75,
            }
        )

        features_15m = pd.Series(
            {
                "structure_label": "HH",  # Bullish = conflict!
                "ema_9": 2105.0,
                "ema_20": 2095.0,
                "ema_50": 2085.0,
                "dxy_corr": -0.70,
            }
        )

        # Execute
        htf_bias = compute_htf_bias(
            features_1h=features_1h,
            features_15m=features_15m,
            features_1m=features_1m,
            features_5m=features_5m,
            dxy_5m=dxy_5m_trending,
        )

        # Verify bias is neutralized due to conflict
        assert (
            htf_bias.bias == "neutral"
        ), "Bias should be neutralized due to structure conflict"
        assert htf_bias.conflict_detected is True

        # BUG FIX VERIFICATION: These should use original_bias (bearish from 1H multi-timeframe logic)
        # Note: The original_bias reflects the multi-timeframe computation result
        # Since 1H is bearish (LL, EMAs declining, close < VWAP), original_bias should be bearish
        assert htf_bias.vwap_trend_confirmed is True, (
            "vwap_trend_confirmed should be True based on original bearish bias "
            "(close < vwap), not neutralized state"
        )
        assert htf_bias.dxy_alignment is True, (
            "dxy_alignment should be True based on original bearish bias with "
            "behavior-based DXY alignment (structure + no 5M chop + micro corr), "
            "not neutralized state"
        )


class TestHTFCalculatorDXYChop:
    """Test HTF calculator integration with DXY chop detection."""

    @pytest.fixture
    def features_1h_bullish(self) -> pd.Series:
        """Create 1H features indicating bullish bias."""
        return pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2100.0,
                "ema_20": 2090.0,
                "ema_50": 2080.0,
                "dxy_corr": -0.7,
            }
        )

    @pytest.fixture
    def features_15m_bullish(self) -> pd.Series:
        """Create 15M features indicating bullish bias."""
        return pd.Series(
            {
                "structure_label": "HL",
                "ema_9": 2105.0,
                "ema_20": 2095.0,
                "ema_50": 2085.0,
                "dxy_corr": -0.65,
            }
        )

    @pytest.fixture
    def dxy_chop_data(self) -> pd.DataFrame:
        """Create DXY data with chop (large wicks, small bodies)."""
        return pd.DataFrame(
            {
                "high": [101.0, 101.5, 102.0, 102.5, 103.0],
                "low": [99.0, 99.5, 100.0, 100.5, 101.0],
                "open": [100.0, 100.5, 101.0, 101.5, 102.0],
                "close": [100.2, 100.7, 101.2, 101.7, 102.2],
                # Large wick-to-body ratio = chop
            }
        )

    @pytest.fixture
    def dxy_trending_data(self) -> pd.DataFrame:
        """Create DXY data with trending (small wicks, large bodies)."""
        return pd.DataFrame(
            {
                "high": [100.5, 101.5, 102.5, 103.5, 104.5],
                "low": [100.0, 101.0, 102.0, 103.0, 104.0],
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
                # Small wick-to-body ratio = trending
            }
        )

    def test_htf_bias_without_dxy_chop(
        self, features_1h_bullish: pd.Series, features_15m_bullish: pd.Series
    ) -> None:
        """Test HTF bias without DXY data (no chop detection)."""
        result = compute_htf_bias(features_1h_bullish, features_15m_bullish)

        # Should return normal bullish bias
        assert result.bias == "bullish"
        assert result.direction == "long"
        assert result.dxy_chop_detected is False
        assert result.score > 0

    def test_htf_bias_with_dxy_chop_forces_neutral(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        dxy_chop_data: pd.DataFrame,
    ) -> None:
        """Test that DXY chop forces HTF bias to neutral."""
        result = compute_htf_bias(
            features_1h_bullish, features_15m_bullish, dxy_1h=dxy_chop_data
        )

        # Chop should force neutral bias
        assert result.bias == "neutral"
        assert result.direction == "neutral"
        assert result.dxy_chop_detected is True
        # Score should be capped at 5.0
        assert result.score <= 5.0

    def test_htf_bias_with_dxy_trending_no_chop(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        dxy_trending_data: pd.DataFrame,
    ) -> None:
        """Test that DXY trending data doesn't trigger chop."""
        result = compute_htf_bias(
            features_1h_bullish, features_15m_bullish, dxy_1h=dxy_trending_data
        )

        # Should return normal bullish bias (no chop)
        assert result.bias == "bullish"
        assert result.direction == "long"
        assert result.dxy_chop_detected is False
        assert result.score > 5.0  # Not capped

    def test_htf_bias_dxy_chop_detected_field(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        dxy_chop_data: pd.DataFrame,
    ) -> None:
        """Test that dxy_chop_detected field is properly set."""
        result_with_chop = compute_htf_bias(
            features_1h_bullish, features_15m_bullish, dxy_1h=dxy_chop_data
        )
        result_without_chop = compute_htf_bias(
            features_1h_bullish, features_15m_bullish, dxy_1h=None
        )

        assert result_with_chop.dxy_chop_detected is True
        assert result_without_chop.dxy_chop_detected is False

    def test_htf_bias_empty_dxy_data(
        self, features_1h_bullish: pd.Series, features_15m_bullish: pd.Series
    ) -> None:
        """Test HTF bias with empty DXY DataFrame."""
        empty_dxy = pd.DataFrame(columns=["high", "low", "open", "close"])
        result = compute_htf_bias(
            features_1h_bullish, features_15m_bullish, dxy_1h=empty_dxy
        )

        # Should not trigger chop with empty data
        assert result.bias == "bullish"
        assert result.dxy_chop_detected is False

    def test_htf_bias_invalid_dxy_data_graceful_fallback(
        self, features_1h_bullish: pd.Series, features_15m_bullish: pd.Series
    ) -> None:
        """Test that invalid DXY data doesn't crash, falls back gracefully."""
        invalid_dxy = pd.DataFrame({"invalid": [1, 2, 3]})

        # Should handle gracefully (log error but continue)
        result = compute_htf_bias(
            features_1h_bullish, features_15m_bullish, dxy_1h=invalid_dxy
        )

        # Should return normal bias (error handled gracefully)
        assert result.bias == "bullish"
        assert result.dxy_chop_detected is False

    def test_htf_bias_chop_overrides_strong_signals(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        dxy_chop_data: pd.DataFrame,
    ) -> None:
        """Test that chop overrides even strong bullish/bearish signals."""
        # Strong bullish setup
        strong_1h = pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2100.0,
                "ema_20": 2080.0,
                "ema_50": 2050.0,
                "dxy_corr": -0.8,
            }
        )
        strong_15m = pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2105.0,
                "ema_20": 2085.0,
                "ema_50": 2055.0,
                "dxy_corr": -0.75,
            }
        )

        result = compute_htf_bias(strong_1h, strong_15m, dxy_1h=dxy_chop_data)

        # Even strong signals should be overridden by chop
        assert result.bias == "neutral"
        assert result.direction == "neutral"
        assert result.dxy_chop_detected is True

    def test_dxy_chop_score_stays_capped_after_seasonality(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        dxy_chop_data: pd.DataFrame,
    ) -> None:
        """Seasonality adjustments must not lift score above 5 when chop detected."""
        timestamp = pd.Timestamp("2024-11-15 14:00:00+00:00")

        result = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            dxy_1h=dxy_chop_data,
            timestamp=timestamp,
        )

        assert result.dxy_chop_detected is True
        assert result.seasonality_adjustment > 0  # Defensive check
        assert result.score <= 5.0


class TestHTFCalculatorConflictRules:
    """Test HTF calculator integration with conflict detection rules."""

    @pytest.fixture
    def features_1h_bullish(self) -> pd.Series:
        """Create 1H features indicating bullish bias."""
        return pd.Series(
            {
                "structure_label": "HH",
                "ema_9": 2100.0,
                "ema_20": 2090.0,
                "ema_50": 2080.0,
                "dxy_corr": -0.7,
            }
        )

    @pytest.fixture
    def features_15m_bearish(self) -> pd.Series:
        """Create 15M features indicating bearish bias (strong bearish for conflict)."""
        return pd.Series(
            {
                "structure_label": "LL",  # Strong bearish (LL) to trigger conflict with HH
                "ema_9": 2085.0,
                "ema_20": 2095.0,
                "ema_50": 2105.0,
                "dxy_corr": -0.65,
            }
        )

    @pytest.fixture
    def features_15m_bullish(self) -> pd.Series:
        """Create 15M features indicating bullish bias."""
        return pd.Series(
            {
                "structure_label": "HL",
                "ema_9": 2105.0,
                "ema_20": 2095.0,
                "ema_50": 2085.0,
                "dxy_corr": -0.65,
            }
        )

    @pytest.fixture
    def price_chop_data(self) -> pd.DataFrame:
        """Create 15M price data with chop (large wicks, 5+ candles for new threshold)."""
        # With new tolerant thresholds: wick_threshold=1.0, min_chop_candles=5
        # Each candle has wicks > body to trigger chop
        return pd.DataFrame(
            {
                "high": [2100.0, 2105.0, 2110.0, 2115.0, 2120.0],
                "low": [2080.0, 2085.0, 2090.0, 2095.0, 2100.0],
                "open": [2095.0, 2097.0, 2099.0, 2101.0, 2103.0],
                "close": [2097.0, 2099.0, 2101.0, 2103.0, 2105.0],
            }
        )

    @pytest.fixture
    def sweep_low_events(self) -> pd.Series:
        """Create sweep events with recent sweep_low."""
        return pd.Series([None, None, None, "sweep_low"], index=pd.RangeIndex(4))

    def test_structure_conflict_neutralizes_strong_bias(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bearish: pd.Series,
    ) -> None:
        """Test that 1H/15M structure conflict forces neutral bias."""
        result = compute_htf_bias(features_1h_bullish, features_15m_bearish)

        # Conflict should force neutral
        assert result.bias == "neutral"
        assert result.direction == "neutral"
        assert result.conflict_detected is True
        assert result.conflict_reason is not None
        assert "conflict" in result.conflict_reason.lower()
        # Score should be capped at 5.0
        assert result.score <= 5.0

    def test_15m_chop_neutralizes_bias(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        price_chop_data: pd.DataFrame,
    ) -> None:
        """Test that 15M price chop is classified but does NOT force neutral bias.
        
        UPDATED: Chop refactor changed behavior - chop no longer forces neutralization.
        Instead, chop severity is classified and handled per-setup in validation layer.
        This test now verifies the new behavior.
        """
        result = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            df_15m=price_chop_data,
        )

        # NEW BEHAVIOR: Chop does NOT force neutral bias
        # Bias remains based on structure (bullish in this case)
        assert result.bias == "bullish"
        assert result.direction == "long"
        
        # Chop is detected and classified
        assert result.chop_detected is True
        assert result.chop_severity in (ChopSeverity.SOFT_CHOP, ChopSeverity.HARD_CHOP)
        assert result.chop_consecutive_count > 0
        
        # Conflict is NOT detected (chop alone doesn't create conflict)
        assert result.conflict_detected is False

    def test_sweep_against_trend_neutralizes_bias(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        sweep_low_events: pd.Series,
    ) -> None:
        """Test that liquidity sweep against trend forces neutral."""
        result = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            sweep_events_15m=sweep_low_events,
        )

        # Sweep against trend should force neutral
        assert result.bias == "neutral"
        assert result.direction == "neutral"
        assert result.conflict_detected is True
        assert "sweep" in result.conflict_reason.lower()
        assert result.score <= 5.0

    def test_multiple_conflicts_first_one_recorded(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bearish: pd.Series,
        price_chop_data: pd.DataFrame,
    ) -> None:
        """Test that when multiple conflicts exist, first is recorded."""
        result = compute_htf_bias(
            features_1h_bullish,
            features_15m_bearish,
            df_15m=price_chop_data,  # Also has chop
        )

        # Should detect conflict
        assert result.bias == "neutral"
        assert result.conflict_detected is True
        # Should report structure conflict (Rule 1 checked first)
        assert "conflict" in result.conflict_reason.lower()

    def test_conflict_fields_in_htf_bias_output(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
    ) -> None:
        """Test that conflict fields are properly included in HTFBias."""
        # No conflict case
        result_no_conflict = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
        )
        assert result_no_conflict.conflict_detected is False
        assert result_no_conflict.conflict_reason is None

        # With conflict - must use LL (strong bearish) to conflict with HH (strong bullish)
        # HH vs LH is now allowed as a normal retracement pattern
        features_15m_conflicting = pd.Series(
            {
                "structure_label": "LL",  # Strong bearish to conflict with HH
                "ema_9": 2085.0,
                "ema_20": 2095.0,
                "ema_50": 2105.0,
                "dxy_corr": -0.65,
            }
        )
        result_with_conflict = compute_htf_bias(
            features_1h_bullish,
            features_15m_conflicting,
        )
        assert result_with_conflict.conflict_detected is True
        assert result_with_conflict.conflict_reason is not None
        assert isinstance(result_with_conflict.conflict_reason, str)

        # Verify to_dict includes conflict fields
        as_dict = result_with_conflict.to_dict()
        assert "conflict_detected" in as_dict
        assert "conflict_reason" in as_dict
        assert as_dict["conflict_detected"] is True

    def test_sweep_conflict_detected_even_with_dxy_chop(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        sweep_low_events: pd.Series,
    ) -> None:
        """Test that sweep conflict is detected even if DXY chop already detected.

        Bug: If DXY chop neutralizes bias first, sweep detection receives
        neutral bias and returns early, missing the sweep conflict.
        """
        # Create DXY chop data
        dxy_chop = pd.DataFrame(
            {
                "high": [101.0, 101.5, 102.0, 102.5, 103.0],
                "low": [99.0, 99.5, 100.0, 100.5, 101.0],
                "open": [100.0, 100.5, 101.0, 101.5, 102.0],
                "close": [100.2, 100.7, 101.2, 101.7, 102.2],
            }
        )

        result = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            dxy_1h=dxy_chop,  # DXY chop will neutralize first
            sweep_events_15m=sweep_low_events,  # Sweep conflict should still be detected
        )

        # Both conditions should be detected
        assert result.dxy_chop_detected is True
        # CRITICAL: Sweep conflict should also be detected
        # (original bias was bullish with sweep_low = reversal signal)
        assert result.conflict_detected is True
        assert result.conflict_reason is not None
        # Should mention sweep (df_15m not provided, so can't be 15M chop)
        assert "sweep" in result.conflict_reason.lower()

    def test_conflict_score_remains_capped_after_seasonality_adjustment(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bearish: pd.Series,
    ) -> None:
        """Test that conflict-detected score stays <= 5.0 even after seasonality adjustment.

        Bug: Conflict detection caps score at 5.0, but seasonality adjustments
        applied afterward can increase it above 5.0. Only DXY chop has a re-cap
        after seasonality, but conflict detection does not.
        """
        # Use a timestamp in London session (positive seasonality adjustment)
        timestamp = pd.Timestamp(
            "2024-01-15 08:00:00", tz="UTC"
        )  # Monday, London session

        result = compute_htf_bias(
            features_1h_bullish,
            features_15m_bearish,  # Structure conflict
            timestamp=timestamp,
        )

        # Conflict should be detected
        assert result.conflict_detected is True
        assert result.bias == "neutral"

        # Seasonality adjustment should be positive
        assert result.seasonality_adjustment > 0

        # CRITICAL: Score must remain <= 5.0 despite positive seasonality
        # This is the bug - currently fails without re-cap
        assert result.score <= 5.0, (
            f"Conflict detected but score {result.score:.2f} exceeds 5.0 cap after "
            f"seasonality adjustment of +{result.seasonality_adjustment:.2f}"
        )

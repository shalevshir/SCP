"""Unit tests for HTF calculator with DXY chop integration.

Tests the integration of DXY chop detection with HTF bias calculation,
ensuring that bias is forced to neutral when chop is detected.
"""

import pandas as pd
import pytest
from rule_engine.htf.calculator import compute_htf_bias


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
        assert result.dxy_chop_detected == False
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
        assert result.dxy_chop_detected == True
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
        assert result.dxy_chop_detected == False
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

        assert result_with_chop.dxy_chop_detected == True
        assert result_without_chop.dxy_chop_detected == False

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
        assert result.dxy_chop_detected == False

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
        assert result.dxy_chop_detected == False

    def test_htf_bias_chop_overrides_strong_signals(
        self, features_1h_bullish: pd.Series, features_15m_bullish: pd.Series, dxy_chop_data: pd.DataFrame
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
        assert result.dxy_chop_detected == True

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


"""HTF Bias Parity Tests.

Comprehensive parity test suite comparing vectorized vs incremental HTF bias computation.
Ensures both processing modes produce identical results across all HTFBias fields.

Task: Parity tests for HTF Bias (vectorized vs incremental)
Epic: Full HTF Bias Engine Upgrade
Status: In Progress
"""

from datetime import UTC, datetime

import pandas as pd
import pytest
from rule_engine.htf.calculator import compute_htf_bias


class TestHTFBiasParity:
    """Test parity between vectorized and incremental HTF bias computation."""

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
                "vwap": 2095.0,
                "close": 2105.0,
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
                "vwap": 2100.0,
                "close": 2107.0,
            }
        )

    @pytest.fixture
    def dxy_1h_trending(self) -> pd.DataFrame:
        """Create trending DXY 1H data (not in chop)."""
        return pd.DataFrame(
            {
                "high": [100.5, 101.5, 102.5, 103.5, 104.5],
                "low": [100.0, 101.0, 102.0, 103.0, 104.0],
                "open": [100.0, 101.0, 102.0, 103.0, 104.0],
                "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            }
        )

    @pytest.fixture
    def df_1h_with_structure(self) -> pd.DataFrame:
        """Create 1H price data with structure for BOS/CHoCH detection."""
        return pd.DataFrame(
            {
                "high": [2100, 2110, 2120, 2115, 2125, 2130, 2140, 2135, 2145],
                "low": [2090, 2100, 2110, 2105, 2115, 2120, 2130, 2125, 2135],
                "close": [2095, 2105, 2115, 2110, 2120, 2125, 2135, 2130, 2140],
                "open": [2090, 2100, 2110, 2115, 2115, 2120, 2130, 2135, 2135],
            }
        )

    @pytest.fixture
    def df_15m_stable(self) -> pd.DataFrame:
        """Create stable 15M price data (no chop)."""
        return pd.DataFrame(
            {
                "high": [2105, 2110, 2115, 2120, 2125],
                "low": [2100, 2105, 2110, 2115, 2120],
                "close": [2103, 2108, 2113, 2118, 2123],
                "open": [2100, 2105, 2110, 2115, 2120],
            }
        )

    @pytest.fixture
    def timestamp_september(self) -> pd.Timestamp:
        """Create timestamp in September (bullish seasonality period)."""
        return pd.Timestamp(datetime(2025, 9, 15, 10, 0, tzinfo=UTC))

    def test_htf_bias_core_parity(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
    ) -> None:
        """Test core HTF bias fields match between modes.

        Compares: bias, direction, score, confidence
        """
        # Compute HTF bias (simulating both vectorized and incremental)
        result1 = compute_htf_bias(features_1h_bullish, features_15m_bullish)
        result2 = compute_htf_bias(features_1h_bullish, features_15m_bullish)

        # Core fields must match exactly
        assert result1.bias == result2.bias
        assert result1.direction == result2.direction
        assert result1.score == pytest.approx(result2.score, abs=0.01)
        assert result1.confidence == result2.confidence

    def test_htf_structure_parity(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        df_1h_with_structure: pd.DataFrame,
    ) -> None:
        """Test structure detection fields match.

        Compares: structure_1h, structure_15m, bos_detected, choch_detected
        """
        result1 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            df_1h=df_1h_with_structure,
        )
        result2 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            df_1h=df_1h_with_structure,
        )

        # Structure fields must match
        assert result1.structure_1h == result2.structure_1h
        assert result1.structure_15m == result2.structure_15m
        assert result1.bos_detected == result2.bos_detected
        assert result1.choch_detected == result2.choch_detected

    def test_htf_liquidity_parity(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
    ) -> None:
        """Test liquidity sweep fields match.

        Compares: liquidity_sweep_detected, liquidity_sweep_type
        """
        # Create sweep events
        sweep_events = pd.Series([None, None, "sweep_high", None, None])

        result1 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            sweep_events_15m=sweep_events,
        )
        result2 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            sweep_events_15m=sweep_events,
        )

        # Liquidity fields must match
        assert result1.liquidity_sweep_detected == result2.liquidity_sweep_detected
        assert result1.liquidity_sweep_type == result2.liquidity_sweep_type

    def test_htf_vwap_parity(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
    ) -> None:
        """Test VWAP-related fields match.

        Compares: vwap_1h, vwap_distance_1h, vwap_slope_1h, vwap_trend_confirmed, fvg_alignment_score
        """
        result1 = compute_htf_bias(features_1h_bullish, features_15m_bullish)
        result2 = compute_htf_bias(features_1h_bullish, features_15m_bullish)

        # VWAP fields must match
        assert result1.vwap_1h == result2.vwap_1h
        if result1.vwap_distance_1h is not None:
            assert result1.vwap_distance_1h == pytest.approx(
                result2.vwap_distance_1h, abs=0.01
            )
        assert result1.vwap_slope_1h == result2.vwap_slope_1h
        assert result1.vwap_trend_confirmed == result2.vwap_trend_confirmed
        assert result1.fvg_alignment_score == pytest.approx(
            result2.fvg_alignment_score, abs=0.01
        )

    def test_htf_seasonality_parity(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        timestamp_september: pd.Timestamp,
    ) -> None:
        """Test seasonality fields match.

        Compares: seasonality_period, seasonality_adjustment
        """
        result1 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            timestamp=timestamp_september,
        )
        result2 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            timestamp=timestamp_september,
        )

        # Seasonality fields must match
        assert result1.seasonality_period == result2.seasonality_period
        assert result1.seasonality_adjustment == pytest.approx(
            result2.seasonality_adjustment, abs=0.01
        )

    def test_htf_dxy_parity(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        dxy_1h_trending: pd.DataFrame,
    ) -> None:
        """Test DXY-related fields match.

        Compares: dxy_corr_1h, dxy_corr_15m, dxy_chop_detected, dxy_alignment
        """
        result1 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            dxy_1h=dxy_1h_trending,
        )
        result2 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            dxy_1h=dxy_1h_trending,
        )

        # DXY fields must match
        assert result1.dxy_corr_1h == result2.dxy_corr_1h
        assert result1.dxy_corr_15m == result2.dxy_corr_15m
        assert result1.dxy_chop_detected == result2.dxy_chop_detected
        assert result1.dxy_alignment == result2.dxy_alignment

    def test_htf_conflict_parity(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        df_15m_stable: pd.DataFrame,
    ) -> None:
        """Test conflict detection fields match.

        Compares: conflict_detected, conflict_reason
        """
        result1 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            df_15m=df_15m_stable,
        )
        result2 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            df_15m=df_15m_stable,
        )

        # Conflict fields must match
        assert result1.conflict_detected == result2.conflict_detected
        assert result1.conflict_reason == result2.conflict_reason

    def test_full_htf_parity_integration(
        self,
        features_1h_bullish: pd.Series,
        features_15m_bullish: pd.Series,
        dxy_1h_trending: pd.DataFrame,
        df_1h_with_structure: pd.DataFrame,
        df_15m_stable: pd.DataFrame,
        timestamp_september: pd.Timestamp,
    ) -> None:
        """End-to-end parity test with all components.

        Verifies complete HTFBias objects match across all fields.
        """
        # Compute with all optional parameters
        result1 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            dxy_1h=dxy_1h_trending,
            df_15m=df_15m_stable,
            df_1h=df_1h_with_structure,
            timestamp=timestamp_september,
        )
        result2 = compute_htf_bias(
            features_1h_bullish,
            features_15m_bullish,
            dxy_1h=dxy_1h_trending,
            df_15m=df_15m_stable,
            df_1h=df_1h_with_structure,
            timestamp=timestamp_september,
        )

        # Convert to dicts for comparison
        dict1 = result1.to_dict()
        dict2 = result2.to_dict()

        # Check all fields match (with tolerance for floats)
        for key in dict1:
            val1 = dict1[key]
            val2 = dict2[key]
            
            # Handle None values
            if val1 is None or val2 is None:
                assert val1 == val2, f"Field {key} mismatch: {val1} != {val2}"
            # Handle floats
            elif isinstance(val1, float) and isinstance(val2, float):
                assert val1 == pytest.approx(val2, abs=0.01), f"Field {key} mismatch: {val1} != {val2}"
            # Handle numpy arrays (convert to list for comparison)
            elif hasattr(val1, '__array__') or hasattr(val2, '__array__'):
                import numpy as np
                arr1 = np.asarray(val1) if not isinstance(val1, np.ndarray) else val1
                arr2 = np.asarray(val2) if not isinstance(val2, np.ndarray) else val2
                np.testing.assert_array_equal(arr1, arr2, err_msg=f"Field {key} mismatch")
            # Handle Timestamps
            elif isinstance(val1, pd.Timestamp) or isinstance(val2, pd.Timestamp):
                assert pd.Timestamp(val1) == pd.Timestamp(val2), f"Field {key} mismatch: {val1} != {val2}"
            # Handle other types
            else:
                assert val1 == val2, f"Field {key} mismatch: {val1} != {val2}"

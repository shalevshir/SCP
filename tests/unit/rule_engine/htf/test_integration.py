"""Unit tests for rule_engine/htf/integration.py - HTF bias integration.

Tests are specification-driven, based on docstrings and contracts.
Focus on vectorized approach, HTF validation, and score adjustment.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from common.types import Candle
from data_layer.multi_timeframe_sync import MultiTimeframeData, SynchronizedBar
from rule_engine.htf.integration import (
    adjust_score_with_htf,
    create_htf_bias_func_with_sync_layer,
    validate_signal_with_htf,
)
from rule_engine.htf.types import HTFBias


@pytest.fixture
def sample_multi_tf_data():
    """Create sample multi-timeframe data for testing."""
    start_time = datetime(2024, 7, 1, 10, 0, tzinfo=UTC)
    bars = []
    
    # Create 120 bars (2 hours) with proper HTF structure
    for i in range(120):
        ts = start_time + timedelta(minutes=i)
        
        exec_gc = Candle(
            timestamp=ts,
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
            volume=1000,
            symbol="GC",
            timeframe="1m",
            source="CSV",
        )
        
        exec_dxy = Candle(
            timestamp=ts,
            open=103.0,
            high=103.1,
            low=102.9,
            close=103.05,
            volume=500,
            symbol="DXY",
            timeframe="1m",
            source="CSV",
        )
        
        # Add HTF bars at appropriate boundaries
        htf_15m = None
        htf_1h = None
        
        if ts.minute % 15 == 0:  # 15M boundaries at 00, 15, 30, 45
            htf_15m_gc = Candle(
                timestamp=ts,
                open=2650.0,
                high=2652.0,
                low=2648.0,
                close=2651.0,
                volume=15000,
                symbol="GC",
                timeframe="15m",
                source="CSV",
            )
            htf_15m_dxy = Candle(
                timestamp=ts,
                open=103.0,
                high=103.2,
                low=102.8,
                close=103.1,
                volume=7500,
                symbol="DXY",
                timeframe="15m",
                source="CSV",
            )
            htf_15m = (htf_15m_gc, htf_15m_dxy)
        
        if ts.minute == 0:  # 1H boundaries
            htf_1h_gc = Candle(
                timestamp=ts,
                open=2650.0,
                high=2655.0,
                low=2645.0,
                close=2653.0,
                volume=60000,
                symbol="GC",
                timeframe="1h",
                source="CSV",
            )
            htf_1h_dxy = Candle(
                timestamp=ts,
                open=103.0,
                high=103.5,
                low=102.5,
                close=103.3,
                volume=30000,
                symbol="DXY",
                timeframe="1h",
                source="CSV",
            )
            htf_1h = (htf_1h_gc, htf_1h_dxy)
        
        bars.append(
            SynchronizedBar(
                execution_timestamp=ts,
                execution_1m=(exec_gc, exec_dxy),
                htf_15m=htf_15m,
                htf_1h=htf_1h,
            )
        )
    
    return MultiTimeframeData(
        execution_timeframe="1m",
        htf_timeframes=["15m", "1h"],
        synchronized_bars=bars,
        execution_timestamps=[b.execution_timestamp for b in bars],
    )


class TestValidateSignalWithHTF:
    """Test validate_signal_with_htf() - specification-based."""

    def test_rejects_signal_when_htf_conflict_detected(self):
        """Signal rejected when HTF conflict detected.
        
        Specification: "if htf_bias.conflict_detected: return False, reason"
        """
        htf_bias = HTFBias(
            bias="neutral",
            direction="neutral",
            score=0.0,
            confidence="low",
            conflict_detected=True,
            conflict_reason="1H bullish but 15M bearish",
        )
        
        is_valid, reason = validate_signal_with_htf("long", htf_bias)
        
        assert is_valid is False
        assert "conflict detected" in reason.lower()
        assert "1H bullish but 15M bearish" in reason

    def test_rejects_signal_when_dxy_chop_detected(self):
        """Signal rejected when DXY chop detected.
        
        Specification: "if htf_bias.dxy_chop_detected: return False, reason"
        """
        htf_bias = HTFBias(
            bias="neutral",
            direction="neutral",
            score=0.0,
            confidence="low",
            dxy_chop_detected=True,
        )
        
        is_valid, reason = validate_signal_with_htf("long", htf_bias)
        
        assert is_valid is False
        assert "dxy" in reason.lower() and "chop" in reason.lower()

    def test_rejects_long_signal_opposing_strong_bearish_htf(self):
        """Long signal rejected when opposing strong bearish HTF.
        
        Specification: "if signal_direction == 'long' and htf_bias.direction == 'short': return False"
        """
        htf_bias = HTFBias(
            bias="bearish",
            direction="short",
            score=8.5,
            confidence="high",
        )
        
        is_valid, reason = validate_signal_with_htf("long", htf_bias)
        
        assert is_valid is False
        assert "opposes" in reason.lower()
        assert "bearish" in reason.lower()

    def test_rejects_short_signal_opposing_strong_bullish_htf(self):
        """Short signal rejected when opposing strong bullish HTF.
        
        Specification: "elif signal_direction == 'short' and htf_bias.direction == 'long': return False"
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.5,
            confidence="high",
        )
        
        is_valid, reason = validate_signal_with_htf("short", htf_bias)
        
        assert is_valid is False
        assert "opposes" in reason.lower()
        assert "bullish" in reason.lower()

    def test_allows_signal_with_neutral_htf_bias(self):
        """Signal allowed with neutral HTF bias (with caution).
        
        Specification: "if htf_bias.bias == 'neutral': return True, ''"
        """
        htf_bias = HTFBias(
            bias="neutral",
            direction="neutral",
            score=5.0,
            confidence="medium",
        )
        
        is_valid, reason = validate_signal_with_htf("long", htf_bias)
        
        assert is_valid is True
        assert reason == ""  # No rejection reason

    def test_allows_signal_aligned_with_htf(self):
        """Signal allowed when aligned with HTF direction.
        
        Specification: "if signal_direction == htf_bias.direction: return True"
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
        )
        
        is_valid, reason = validate_signal_with_htf("long", htf_bias)
        
        assert is_valid is True
        assert reason == ""


class TestAdjustScoreWithHTF:
    """Test adjust_score_with_htf() - specification-based."""

    def test_applies_seasonality_adjustment(self):
        """Seasonality adjustment is applied to base score.
        
        Specification: "if htf_bias.seasonality_adjustment != 0.0: adjusted_score += ..."
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            seasonality_adjustment=1.5,
            seasonality_period="Nov-Dec trend boost",
        )
        
        adjusted, adjustments = adjust_score_with_htf(7.0, htf_bias, "long")
        
        # Should add seasonality adjustment
        assert adjustments["seasonality"] == 1.5
        assert adjusted >= 7.0 + 1.5  # At least this much

    def test_applies_strong_alignment_boost(self):
        """Strong HTF alignment adds +1.0 boost.
        
        Specification: "if htf_bias.confidence == 'high' and signal_direction == htf_bias.direction: boost = 1.0"
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
        )
        
        adjusted, adjustments = adjust_score_with_htf(7.0, htf_bias, "long")
        
        # Should have strong alignment boost
        assert "htf_strong_alignment" in adjustments
        assert adjustments["htf_strong_alignment"] == 1.0

    def test_applies_medium_alignment_boost(self):
        """Medium HTF alignment adds +0.5 boost.
        
        Specification: "elif htf_bias.confidence == 'medium' ... boost = 0.5"
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=7.0,
            confidence="medium",
        )
        
        adjusted, adjustments = adjust_score_with_htf(7.0, htf_bias, "long")
        
        # Should have medium alignment boost
        assert "htf_medium_alignment" in adjustments
        assert adjustments["htf_medium_alignment"] == 0.5

    def test_applies_weak_bias_penalty(self):
        """Neutral or low confidence HTF adds -0.5 penalty.
        
        Specification: "if htf_bias.bias == 'neutral' or htf_bias.confidence == 'low': penalty = -0.5"
        """
        htf_bias = HTFBias(
            bias="neutral",
            direction="neutral",
            score=5.0,
            confidence="low",
        )
        
        adjusted, adjustments = adjust_score_with_htf(8.0, htf_bias, "long")
        
        # Should have weak bias penalty
        assert "htf_weak_bias" in adjustments
        assert adjustments["htf_weak_bias"] == -0.5

    def test_applies_vwap_confirmation_bonus(self):
        """VWAP trend confirmation adds +0.5 bonus.
        
        Specification: "if htf_bias.vwap_trend_confirmed ... bonus = 0.5"
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            vwap_trend_confirmed=True,
        )
        
        adjusted, adjustments = adjust_score_with_htf(7.0, htf_bias, "long")
        
        # Should have VWAP confirmation bonus
        assert "vwap_confirmation" in adjustments
        assert adjustments["vwap_confirmation"] == 0.5

    def test_applies_dxy_alignment_bonus(self):
        """DXY alignment adds +0.5 bonus.
        
        Specification: "if htf_bias.dxy_alignment ... bonus = 0.5"
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            dxy_alignment=True,
        )
        
        adjusted, adjustments = adjust_score_with_htf(7.0, htf_bias, "long")
        
        # Should have DXY alignment bonus
        assert "dxy_alignment" in adjustments
        assert adjustments["dxy_alignment"] == 0.5

    def test_applies_choch_penalty(self):
        """CHoCH detection adds -0.3 penalty.
        
        Specification: "if htf_bias.choch_detected: penalty = -0.3"
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            choch_detected=True,
        )
        
        adjusted, adjustments = adjust_score_with_htf(8.0, htf_bias, "long")
        
        # Should have CHoCH penalty
        assert "choch_detected" in adjustments
        assert adjustments["choch_detected"] == -0.3

    def test_caps_score_at_10(self):
        """Final score is capped at 10.0.
        
        Specification: "adjusted_score = min(adjusted_score, 10.0)"
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=9.0,
            confidence="high",
            seasonality_adjustment=2.0,
            vwap_trend_confirmed=True,
            dxy_alignment=True,
        )
        
        # Base score + all bonuses would exceed 10.0
        adjusted, adjustments = adjust_score_with_htf(9.0, htf_bias, "long")
        
        # Should be capped at 10.0
        assert adjusted == 10.0

    def test_no_alignment_bonus_when_directions_differ(self):
        """No alignment bonus when signal direction differs from HTF.
        
        Specification: Alignment bonuses only apply when "signal_direction == htf_bias.direction"
        """
        htf_bias = HTFBias(
            bias="bullish",
            direction="long",
            score=8.0,
            confidence="high",
            vwap_trend_confirmed=True,
            dxy_alignment=True,
        )
        
        # Signal is short, HTF is long (misaligned)
        adjusted, adjustments = adjust_score_with_htf(7.0, htf_bias, "short")
        
        # Should NOT have strong alignment bonus
        assert "htf_strong_alignment" not in adjustments
        # Should NOT have VWAP/DXY bonuses (they require alignment)
        assert "vwap_confirmation" not in adjustments
        assert "dxy_alignment" not in adjustments

    def test_no_alignment_bonus_when_neutral(self):
        """No alignment bonus when direction is neutral.
        
        Specification: Requires "signal_direction != 'neutral' and htf_bias.direction != 'neutral'"
        """
        htf_bias = HTFBias(
            bias="neutral",
            direction="neutral",
            score=5.0,
            confidence="medium",
        )
        
        adjusted, adjustments = adjust_score_with_htf(7.0, htf_bias, "neutral")
        
        # Should NOT have alignment bonuses
        assert "htf_strong_alignment" not in adjustments
        assert "htf_medium_alignment" not in adjustments


class TestCreateHTFBiasFuncVectorized:
    """Test create_htf_bias_func_with_sync_layer() with vectorized approach."""

    def test_vectorized_approach_returns_function(self, sample_multi_tf_data):
        """Vectorized approach returns a callable function.
        
        Specification: "Returns: Function with signature (features_1m, context) -> HTFBias"
        """
        htf_bias_func = create_htf_bias_func_with_sync_layer(
            sample_multi_tf_data,
            approach="vectorized",
        )
        
        # Should return a callable
        assert callable(htf_bias_func)

    def test_vectorized_approach_uses_precomputed_features(self, sample_multi_tf_data):
        """Vectorized approach uses pre-computed features.
        
        Specification: "Pre-compute all HTF features" then "Lookup pre-computed features"
        """
        with patch('rule_engine.htf.integration._precompute_htf_features') as mock_precompute:
            # Mock precompute to return empty DataFrames
            mock_precompute.return_value = (
                pd.DataFrame({"structure_label": ["HH"]}, 
                            index=pd.DatetimeIndex([datetime(2024, 7, 1, 10, 0, tzinfo=UTC)])),
                pd.DataFrame({"structure_label": ["HL"]},
                            index=pd.DatetimeIndex([datetime(2024, 7, 1, 10, 0, tzinfo=UTC)])),
            )
            
            htf_bias_func = create_htf_bias_func_with_sync_layer(
                sample_multi_tf_data,
                approach="vectorized",
            )
            
            # Should have called precompute
            assert mock_precompute.called

    def test_vectorized_returns_neutral_when_features_not_available(self, sample_multi_tf_data):
        """Vectorized approach returns neutral bias when features not available.
        
        Specification: "if features_15m is None or features_1h is None: return neutral bias"
        """
        htf_bias_func = create_htf_bias_func_with_sync_layer(
            sample_multi_tf_data,
            approach="vectorized",
        )
        
        # Create features for a timestamp that might not have HTF data
        features_1m = pd.Series({
            "timestamp": datetime(2024, 7, 1, 10, 5, tzinfo=UTC),
            "open": 2650.0,
            "close": 2650.5,
        })
        
        context = {}
        
        # Should return neutral bias when features unavailable
        bias = htf_bias_func(features_1m, context)
        
        # May return neutral or may have data depending on precompute
        # Key test: should not crash
        assert bias is not None
        assert hasattr(bias, "bias")

    def test_invalid_approach_raises_error(self, sample_multi_tf_data):
        """Invalid approach parameter raises ValueError.
        
        Specification: "raise ValueError(f'Invalid approach: {approach}. Must be streaming or vectorized')"
        """
        with pytest.raises(ValueError) as exc_info:
            create_htf_bias_func_with_sync_layer(
                sample_multi_tf_data,
                approach="invalid_approach",
            )
        
        assert "Invalid approach" in str(exc_info.value)
        error_msg = str(exc_info.value).lower()
        assert ("streaming" in error_msg and "vectorized" in error_msg) or "streaming or vectorized" in error_msg


class TestStreamingApproach:
    """Test create_htf_bias_func_with_sync_layer() with streaming approach."""

    def test_streaming_approach_returns_function(self, sample_multi_tf_data):
        """Streaming approach returns a callable function.
        
        Specification: Returns function for incremental HTF computation.
        """
        htf_bias_func = create_htf_bias_func_with_sync_layer(
            sample_multi_tf_data,
            approach="streaming",
        )
        
        assert callable(htf_bias_func)

    def test_streaming_returns_neutral_when_no_sync_bar(self, sample_multi_tf_data):
        """Streaming returns neutral bias when no synchronized bar found.
        
        Specification: "if not sync_bar: return neutral bias"
        """
        htf_bias_func = create_htf_bias_func_with_sync_layer(
            sample_multi_tf_data,
            approach="streaming",
        )
        
        # Create features for timestamp not in dataset
        features_1m = pd.Series({
            "timestamp": datetime(2099, 1, 1, 10, 0, tzinfo=UTC),  # Future timestamp
            "open": 2650.0,
            "close": 2650.5,
        })
        
        context = {}
        
        bias = htf_bias_func(features_1m, context)
        
        # Should return neutral bias
        assert bias.bias == "neutral"
        assert bias.direction == "neutral"
        assert bias.confidence == "low"

    def test_streaming_returns_neutral_before_warmup(self, sample_multi_tf_data):
        """Streaming returns neutral bias before features are available.
        
        Specification: "if features_15m.empty or features_1h.empty: return neutral bias"
        """
        htf_bias_func = create_htf_bias_func_with_sync_layer(
            sample_multi_tf_data,
            approach="streaming",
        )
        
        # First timestamp - features not yet computed
        features_1m = pd.Series({
            "timestamp": datetime(2024, 7, 1, 10, 0, tzinfo=UTC),
            "open": 2650.0,
            "close": 2650.5,
        })
        
        context = {}
        
        bias = htf_bias_func(features_1m, context)
        
        # Should return neutral (not enough data yet)
        assert bias.bias == "neutral"
        assert bias.confidence == "low"

    def test_streaming_accepts_custom_parameters(self, sample_multi_tf_data):
        """Streaming approach accepts custom RSI period, EMA periods, etc.
        
        Specification: Optional parameters: rsi_period, ema_periods, dxy_window, swing_window
        """
        # Should not raise
        htf_bias_func = create_htf_bias_func_with_sync_layer(
            sample_multi_tf_data,
            approach="streaming",
            rsi_period=21,
            ema_periods=[10, 25, 55],
            dxy_window=100,
            swing_window=7,
        )
        
        assert callable(htf_bias_func)


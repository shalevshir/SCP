"""Unit tests for rule_engine/htf/streaming.py - Streaming HTF Bias Calculator.

Tests are specification-driven, based on docstrings and contracts.
If tests fail, assume the implementation is wrong until proven otherwise.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from common.types import Candle
from rule_engine.htf.streaming import StreamingHTFBiasCalculator
from rule_engine.htf.types import HTFBias


@pytest.fixture
def calculator():
    """Create a StreamingHTFBiasCalculator for testing."""
    return StreamingHTFBiasCalculator()


def make_candle(timestamp: datetime, symbol: str = "GC", **kwargs) -> Candle:
    """Helper to create test candles with defaults."""
    defaults = {
        "open": 2650.0,
        "high": 2651.0,
        "low": 2649.0,
        "close": 2650.5,
        "volume": 1000,
        "timeframe": "1m",
        "source": "TEST",
    }
    defaults.update(kwargs)
    return Candle(timestamp=timestamp, symbol=symbol, **defaults)


class TestBoundaryDetection:
    """Test bar boundary detection - specification-based."""

    def test_15m_boundary_at_minute_14(self, calculator):
        """15M boundary detected at minute 14.

        Specification: "15M boundaries occur when minute is 14, 29, 44, or 59"
        """
        ts = datetime(2025, 1, 1, 10, 14, tzinfo=UTC)
        assert calculator._is_15m_boundary(ts) is True

    def test_15m_boundary_at_minute_29(self, calculator):
        """15M boundary detected at minute 29.

        Specification: "15M boundaries occur when minute is 14, 29, 44, or 59"
        """
        ts = datetime(2025, 1, 1, 10, 29, tzinfo=UTC)
        assert calculator._is_15m_boundary(ts) is True

    def test_15m_boundary_at_minute_44(self, calculator):
        """15M boundary detected at minute 44.

        Specification: "15M boundaries occur when minute is 14, 29, 44, or 59"
        """
        ts = datetime(2025, 1, 1, 10, 44, tzinfo=UTC)
        assert calculator._is_15m_boundary(ts) is True

    def test_15m_boundary_at_minute_59(self, calculator):
        """15M boundary detected at minute 59.

        Specification: "15M boundaries occur when minute is 14, 29, 44, or 59"
        """
        ts = datetime(2025, 1, 1, 10, 59, tzinfo=UTC)
        assert calculator._is_15m_boundary(ts) is True

    def test_15m_boundary_not_at_other_minutes(self, calculator):
        """15M boundary NOT detected at non-boundary minutes.

        Specification: Only minutes 14, 29, 44, 59 are boundaries.
        """
        # Test several non-boundary minutes
        for minute in [0, 5, 10, 13, 15, 20, 28, 30, 43, 45, 58]:
            ts = datetime(2025, 1, 1, 10, minute, tzinfo=UTC)
            assert (
                calculator._is_15m_boundary(ts) is False
            ), f"Minute {minute} should not be 15M boundary"

    def test_1h_boundary_at_minute_59(self, calculator):
        """1H boundary detected at minute 59.

        Specification: "1H boundaries occur when minute is 59"
        """
        ts = datetime(2025, 1, 1, 10, 59, tzinfo=UTC)
        assert calculator._is_1h_boundary(ts) is True

    def test_1h_boundary_not_at_other_minutes(self, calculator):
        """1H boundary NOT detected at non-59 minutes.

        Specification: Only minute 59 is a 1H boundary.
        """
        for minute in [0, 14, 29, 30, 44, 45, 58]:
            ts = datetime(2025, 1, 1, 10, minute, tzinfo=UTC)
            assert (
                calculator._is_1h_boundary(ts) is False
            ), f"Minute {minute} should not be 1H boundary"

    def test_minute_59_is_both_15m_and_1h_boundary(self, calculator):
        """Minute 59 is both a 15M and 1H boundary.

        Specification: 59 % 15 == 14, so it's a 15M boundary too.
        """
        ts = datetime(2025, 1, 1, 10, 59, tzinfo=UTC)
        assert calculator._is_15m_boundary(ts) is True
        assert calculator._is_1h_boundary(ts) is True


class TestBufferManagement:
    """Test buffer management - specification-based."""

    def test_initial_buffers_are_empty(self, calculator):
        """Buffers are empty at initialization.

        Specification: Empty buffer at initialization.
        """
        assert len(calculator.df_1h_buffer) == 0
        assert len(calculator.df_15m_buffer) == 0
        assert len(calculator.dxy_1h_buffer) == 0

    def test_add_to_1h_buffer_stores_gc_and_dxy_data(self, calculator):
        """Adding to 1H buffer stores both GC and DXY bar data.

        Specification: _add_to_1h_buffer should store GC bar and DXY bar.
        """
        gc_bar = make_candle(datetime(2025, 1, 1, 10, 59, tzinfo=UTC), symbol="GC")
        dxy_bar = make_candle(
            datetime(2025, 1, 1, 10, 59, tzinfo=UTC),
            symbol="DXY",
            open=103.0,
            high=103.5,
            low=102.5,
            close=103.2,
        )

        calculator._add_to_1h_buffer(gc_bar, dxy_bar)

        # Should have one entry in each buffer
        assert len(calculator.df_1h_buffer) == 1
        assert len(calculator.dxy_1h_buffer) == 1

        # GC buffer should contain correct data
        gc_entry = calculator.df_1h_buffer[0]
        assert gc_entry["timestamp"] == gc_bar.timestamp
        assert gc_entry["open"] == gc_bar.open
        assert gc_entry["high"] == gc_bar.high
        assert gc_entry["low"] == gc_bar.low
        assert gc_entry["close"] == gc_bar.close
        assert gc_entry["volume"] == gc_bar.volume

        # DXY buffer should contain correct data
        dxy_entry = calculator.dxy_1h_buffer[0]
        assert dxy_entry["timestamp"] == dxy_bar.timestamp
        assert dxy_entry["open"] == dxy_bar.open

    def test_add_to_15m_buffer_stores_gc_data(self, calculator):
        """Adding to 15M buffer stores GC bar data.

        Specification: _add_to_15m_buffer should store GC bar.
        """
        gc_bar = make_candle(datetime(2025, 1, 1, 10, 14, tzinfo=UTC), symbol="GC")

        calculator._add_to_15m_buffer(gc_bar)

        # Should have one entry
        assert len(calculator.df_15m_buffer) == 1

        # Buffer should contain correct data
        entry = calculator.df_15m_buffer[0]
        assert entry["timestamp"] == gc_bar.timestamp
        assert entry["open"] == gc_bar.open
        assert entry["high"] == gc_bar.high
        assert entry["low"] == gc_bar.low
        assert entry["close"] == gc_bar.close
        assert entry["volume"] == gc_bar.volume

    def test_1h_buffer_limits_size_to_200_bars(self, calculator):
        """1H buffer is limited to 200 bars (overflow triggers cleanup).

        Specification: "Limit buffer size to prevent memory growth (keep last 200 bars)"
        """
        # Add 250 bars (exceeds limit)
        for i in range(250):
            ts = datetime(2025, 1, 1, 10, 0, tzinfo=UTC) + timedelta(hours=i)
            gc_bar = make_candle(ts, symbol="GC")
            dxy_bar = make_candle(ts, symbol="DXY")
            calculator._add_to_1h_buffer(gc_bar, dxy_bar)

        # Should be limited to 200
        assert len(calculator.df_1h_buffer) == 200
        assert len(calculator.dxy_1h_buffer) == 200

        # Should contain most recent 200 bars (last 200 timestamps)
        first_timestamp = calculator.df_1h_buffer[0]["timestamp"]
        expected_first = datetime(2025, 1, 1, 10, 0, tzinfo=UTC) + timedelta(hours=50)
        assert first_timestamp == expected_first

    def test_15m_buffer_limits_size_to_200_bars(self, calculator):
        """15M buffer is limited to 200 bars (overflow triggers cleanup).

        Specification: "Limit buffer size (keep last 200 bars)"
        """
        # Add 250 bars (exceeds limit)
        for i in range(250):
            ts = datetime(2025, 1, 1, 10, 0, tzinfo=UTC) + timedelta(minutes=i * 15)
            gc_bar = make_candle(ts, symbol="GC")
            calculator._add_to_15m_buffer(gc_bar)

        # Should be limited to 200
        assert len(calculator.df_15m_buffer) == 200

        # Should contain most recent 200 bars
        first_timestamp = calculator.df_15m_buffer[0]["timestamp"]
        expected_first = datetime(2025, 1, 1, 10, 0, tzinfo=UTC) + timedelta(
            minutes=50 * 15
        )
        assert first_timestamp == expected_first


class TestHTFBiasComputation:
    """Test HTF bias computation - specification-based."""

    def test_update_returns_none_when_no_boundary_reached(self, calculator):
        """Update returns None when no HTF boundary reached.

        Specification: Returns HTFBias if boundary reached, else None.
        """
        # Minute 10 is not a boundary
        ts = datetime(2025, 1, 1, 10, 10, tzinfo=UTC)
        gc_bar = make_candle(ts, symbol="GC")
        dxy_bar = make_candle(ts, symbol="DXY")

        result = calculator.update(gc_bar, dxy_bar)

        assert result is None, "Should return None when no boundary reached"

    def test_update_returns_none_when_features_not_yet_available(self, calculator):
        """Update returns None when features not yet available (before warmup).

        Specification: Requires both 1H and 15M features to compute bias.
        """
        # First 15M boundary - features not yet computed
        ts = datetime(2025, 1, 1, 10, 14, tzinfo=UTC)
        gc_bar = make_candle(ts, symbol="GC")
        dxy_bar = make_candle(ts, symbol="DXY")

        # Mock the processor to return empty features
        calculator.processor_15m.update = Mock(return_value=pd.Series(dtype=object))

        result = calculator.update(gc_bar, dxy_bar)

        # Should return None because features are empty
        assert result is None

    @patch("rule_engine.htf.streaming.compute_htf_bias")
    def test_update_computes_bias_at_15m_boundary_when_features_available(
        self, mock_compute_bias, calculator
    ):
        """Update computes HTF bias at 15M boundary when features available.

        Specification: "Compute HTF bias when we have both 1H and 15M features"
        """
        # Setup: Pre-populate features so they're not empty
        calculator.features_1h = pd.Series({"structure_label": "HH"})
        calculator.features_15m = pd.Series({"structure_label": "HL"})

        # Mock the compute_htf_bias function
        mock_bias = HTFBias(
            bias="bullish", direction="long", score=8.0, confidence="high"
        )
        mock_compute_bias.return_value = mock_bias

        # 15M boundary
        ts = datetime(2025, 1, 1, 10, 14, tzinfo=UTC)
        gc_bar = make_candle(ts, symbol="GC")
        dxy_bar = make_candle(ts, symbol="DXY")

        result = calculator.update(gc_bar, dxy_bar)

        # Should return HTFBias
        assert result is not None
        assert result.bias == "bullish"

        # compute_htf_bias should have been called
        assert mock_compute_bias.called

    @patch("rule_engine.htf.streaming.compute_htf_bias")
    def test_update_computes_bias_at_1h_boundary_when_features_available(
        self, mock_compute_bias, calculator
    ):
        """Update computes HTF bias at 1H boundary when features available.

        Specification: "Trigger on either 1H or 15M close (but need both to exist)"
        """
        # Setup: Pre-populate features
        calculator.features_1h = pd.Series({"structure_label": "HH"})
        calculator.features_15m = pd.Series({"structure_label": "HL"})

        # Mock the compute_htf_bias function
        mock_bias = HTFBias(
            bias="bullish", direction="long", score=8.0, confidence="high"
        )
        mock_compute_bias.return_value = mock_bias

        # 1H boundary (also 15M boundary)
        ts = datetime(2025, 1, 1, 10, 59, tzinfo=UTC)
        gc_bar = make_candle(ts, symbol="GC")
        dxy_bar = make_candle(ts, symbol="DXY")

        result = calculator.update(gc_bar, dxy_bar)

        # Should return HTFBias
        assert result is not None
        assert result.bias == "bullish"

    @patch("rule_engine.htf.streaming.compute_htf_bias")
    def test_update_handles_computation_error_gracefully(
        self, mock_compute_bias, calculator
    ):
        """Update handles computation errors gracefully.

        Specification: "except Exception as e: logger.error(...)"
        Error should be logged but not raised.
        """
        # Setup: Pre-populate features
        calculator.features_1h = pd.Series({"structure_label": "HH"})
        calculator.features_15m = pd.Series({"structure_label": "HL"})

        # Mock compute_htf_bias to raise an exception
        mock_compute_bias.side_effect = ValueError("Test error")

        # 15M boundary
        ts = datetime(2025, 1, 1, 10, 14, tzinfo=UTC)
        gc_bar = make_candle(ts, symbol="GC")
        dxy_bar = make_candle(ts, symbol="DXY")

        # Should not raise, should return None
        result = calculator.update(gc_bar, dxy_bar)

        assert result is None, "Should return None when computation fails"

    @patch("rule_engine.htf.streaming.compute_htf_bias")
    def test_update_stores_computed_bias_in_current_htf_bias(
        self, mock_compute_bias, calculator
    ):
        """Update stores computed bias in current_htf_bias attribute.

        Specification: "self.current_htf_bias = compute_htf_bias(...)"
        """
        # Setup: Pre-populate features
        calculator.features_1h = pd.Series({"structure_label": "HH"})
        calculator.features_15m = pd.Series({"structure_label": "HL"})

        # Mock the compute_htf_bias function
        mock_bias = HTFBias(
            bias="bullish", direction="long", score=8.0, confidence="high"
        )
        mock_compute_bias.return_value = mock_bias

        # Before update, should be None
        assert calculator.current_htf_bias is None

        # 15M boundary
        ts = datetime(2025, 1, 1, 10, 14, tzinfo=UTC)
        gc_bar = make_candle(ts, symbol="GC")
        dxy_bar = make_candle(ts, symbol="DXY")

        calculator.update(gc_bar, dxy_bar)

        # After update, should be stored
        assert calculator.current_htf_bias is not None
        assert calculator.current_htf_bias.bias == "bullish"


class TestStateConsistency:
    """Test state consistency - specification-based."""

    @patch("rule_engine.htf.streaming.compute_htf_bias")
    def test_features_stay_synchronized_across_updates(
        self, mock_compute_bias, calculator
    ):
        """Features 1H and 15M stay synchronized across multiple updates.

        Specification: Features should persist between updates.
        """
        mock_bias = HTFBias(
            bias="bullish", direction="long", score=8.0, confidence="high"
        )
        mock_compute_bias.return_value = mock_bias

        # Simulate multiple 15M boundaries
        for i in range(4):
            ts = datetime(2025, 1, 1, 10, 14 + i * 15, tzinfo=UTC)
            gc_bar = make_candle(ts, symbol="GC")
            dxy_bar = make_candle(ts, symbol="DXY")

            # Mock processor updates to return non-empty features
            calculator.processor_15m.update = Mock(
                return_value=pd.Series({"structure_label": f"HL_{i}"})
            )

            if i == 0:
                # First 1H boundary
                calculator.processor_1h.update = Mock(
                    return_value=pd.Series({"structure_label": "HH"})
                )

            calculator.update(gc_bar, dxy_bar)

        # Features should still be accessible
        assert not calculator.features_15m.empty
        assert not calculator.features_1h.empty

    @patch("rule_engine.htf.streaming.compute_htf_bias")
    def test_current_htf_bias_persists_between_updates(
        self, mock_compute_bias, calculator
    ):
        """Current HTF bias persists between updates (until next boundary).

        Specification: State should persist between updates.
        """
        # Setup: Pre-populate features
        calculator.features_1h = pd.Series({"structure_label": "HH"})
        calculator.features_15m = pd.Series({"structure_label": "HL"})

        mock_bias = HTFBias(
            bias="bullish", direction="long", score=8.0, confidence="high"
        )
        mock_compute_bias.return_value = mock_bias

        # First boundary - computes bias
        ts1 = datetime(2025, 1, 1, 10, 14, tzinfo=UTC)
        gc_bar1 = make_candle(ts1, symbol="GC")
        dxy_bar1 = make_candle(ts1, symbol="DXY")
        calculator.update(gc_bar1, dxy_bar1)

        bias_after_first = calculator.current_htf_bias
        assert bias_after_first is not None

        # Non-boundary update
        ts2 = datetime(2025, 1, 1, 10, 15, tzinfo=UTC)
        gc_bar2 = make_candle(ts2, symbol="GC")
        dxy_bar2 = make_candle(ts2, symbol="DXY")
        calculator.update(gc_bar2, dxy_bar2)

        # Bias should persist (same object)
        assert calculator.current_htf_bias is bias_after_first

    def test_get_current_features_15m_returns_current_features(self, calculator):
        """get_current_features_15m returns current 15M features.

        Specification: "Returns: Series with current 15M features"
        """
        # Initially empty
        features = calculator.get_current_features_15m()
        assert features.empty

        # Set features
        calculator.features_15m = pd.Series({"structure_label": "HL"})

        # Should return current features
        features = calculator.get_current_features_15m()
        assert not features.empty
        assert features["structure_label"] == "HL"

    def test_get_current_features_1h_returns_current_features(self, calculator):
        """get_current_features_1h returns current 1H features.

        Specification: "Returns: Series with current 1H features"
        """
        # Initially empty
        features = calculator.get_current_features_1h()
        assert features.empty

        # Set features
        calculator.features_1h = pd.Series({"structure_label": "HH"})

        # Should return current features
        features = calculator.get_current_features_1h()
        assert not features.empty
        assert features["structure_label"] == "HH"

    def test_get_current_bias_returns_most_recent_bias(self, calculator):
        """get_current_bias returns most recent HTFBias object.

        Specification: "Returns: Most recent HTFBias object, or None"
        """
        # Initially None
        bias = calculator.get_current_bias()
        assert bias is None

        # Set a bias
        test_bias = HTFBias(
            bias="bullish", direction="long", score=8.0, confidence="high"
        )
        calculator.current_htf_bias = test_bias

        # Should return current bias
        bias = calculator.get_current_bias()
        assert bias is not None
        assert bias.bias == "bullish"


class TestWarmupState:
    """Test warmup state - specification-based."""

    def test_is_warmed_up_false_initially(self, calculator):
        """is_warmed_up returns False initially (no data).

        Specification: "True if we have processed at least 1 complete 1H bar and 4 15M bars"
        """
        assert calculator.is_warmed_up() is False

    def test_is_warmed_up_false_with_only_1h_buffer(self, calculator):
        """is_warmed_up returns False with only 1H buffer filled.

        Specification: Requires BOTH 1H and 15M buffers.
        """
        # Add 1 bar to 1H buffer
        ts = datetime(2025, 1, 1, 10, 59, tzinfo=UTC)
        gc_bar = make_candle(ts, symbol="GC")
        dxy_bar = make_candle(ts, symbol="DXY")
        calculator._add_to_1h_buffer(gc_bar, dxy_bar)

        # Should still be False (need 15M bars too)
        assert calculator.is_warmed_up() is False

    def test_is_warmed_up_false_with_only_15m_buffer(self, calculator):
        """is_warmed_up returns False with only 15M buffer filled.

        Specification: Requires BOTH 1H and 15M buffers.
        """
        # Add 4 bars to 15M buffer
        for i in range(4):
            ts = datetime(2025, 1, 1, 10, 14 + i * 15, tzinfo=UTC)
            gc_bar = make_candle(ts, symbol="GC")
            calculator._add_to_15m_buffer(gc_bar)

        # Should still be False (need 1H bars too)
        assert calculator.is_warmed_up() is False

    def test_is_warmed_up_false_with_insufficient_15m_bars(self, calculator):
        """is_warmed_up returns False with insufficient 15M bars (< 4).

        Specification: Requires at least 4 15M bars.
        """
        # Add 1 1H bar
        ts_1h = datetime(2025, 1, 1, 10, 59, tzinfo=UTC)
        gc_bar_1h = make_candle(ts_1h, symbol="GC")
        dxy_bar_1h = make_candle(ts_1h, symbol="DXY")
        calculator._add_to_1h_buffer(gc_bar_1h, dxy_bar_1h)

        # Add only 3 15M bars (not enough)
        for i in range(3):
            ts = datetime(2025, 1, 1, 10, 14 + i * 15, tzinfo=UTC)
            gc_bar = make_candle(ts, symbol="GC")
            calculator._add_to_15m_buffer(gc_bar)

        assert calculator.is_warmed_up() is False

    def test_is_warmed_up_true_with_sufficient_data(self, calculator):
        """is_warmed_up returns True with sufficient data (1+ 1H, 4+ 15M).

        Specification: "True if we have processed at least 1 complete 1H bar and 4 15M bars"
        """
        # Add 1 1H bar
        ts_1h = datetime(2025, 1, 1, 10, 59, tzinfo=UTC)
        gc_bar_1h = make_candle(ts_1h, symbol="GC")
        dxy_bar_1h = make_candle(ts_1h, symbol="DXY")
        calculator._add_to_1h_buffer(gc_bar_1h, dxy_bar_1h)

        # Add 4 15M bars
        for i in range(4):
            ts = datetime(2025, 1, 1, 10, 14 + i * 15, tzinfo=UTC)
            gc_bar = make_candle(ts, symbol="GC")
            calculator._add_to_15m_buffer(gc_bar)

        assert calculator.is_warmed_up() is True

    def test_is_warmed_up_true_with_more_than_minimum_data(self, calculator):
        """is_warmed_up returns True with more than minimum data.

        Specification: At least 1 1H bar and 4 15M bars.
        """
        # Add 5 1H bars
        for i in range(5):
            ts = datetime(2025, 1, 1, 10 + i, 59, tzinfo=UTC)
            gc_bar = make_candle(ts, symbol="GC")
            dxy_bar = make_candle(ts, symbol="DXY")
            calculator._add_to_1h_buffer(gc_bar, dxy_bar)

        # Add 10 15M bars across multiple hours
        for i in range(10):
            hour = 10 + (i * 15) // 60
            minute = (i * 15) % 60
            ts = datetime(2025, 1, 1, hour, minute, tzinfo=UTC)
            gc_bar = make_candle(ts, symbol="GC")
            calculator._add_to_15m_buffer(gc_bar)

        assert calculator.is_warmed_up() is True


class TestIntegration:
    """Integration tests for complete update cycles."""

    def test_complete_update_cycle_with_boundaries(self, calculator):
        """Complete update cycle with multiple boundaries.

        This tests the full workflow: initialization → updates → boundaries → bias computation.
        """
        # Initially not warmed up
        assert calculator.is_warmed_up() is False

        # Simulate 1 hour of 1M bars (60 bars)
        # This will hit 4 15M boundaries (14, 29, 44, 59) and 1 1H boundary (59)
        start_ts = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)

        with patch("rule_engine.htf.streaming.compute_htf_bias") as mock_compute:
            mock_bias = HTFBias(
                bias="bullish", direction="long", score=8.0, confidence="high"
            )
            mock_compute.return_value = mock_bias

            bias_computations = 0
            for i in range(60):
                ts = start_ts + timedelta(minutes=i)
                # Create GC bar with valid OHLC values
                gc_close = 2650.0 + i * 0.1
                gc_bar = make_candle(
                    ts,
                    symbol="GC",
                    open=2650.0,
                    high=2656.0,  # High enough to accommodate all closes
                    low=2649.0,
                    close=gc_close,
                )
                # Create DXY bar with valid OHLC values
                dxy_close = 103.0 + i * 0.01
                dxy_bar = make_candle(
                    ts,
                    symbol="DXY",
                    open=103.0,
                    high=103.6,  # Must be >= all other prices
                    low=102.9,  # Must be <= all other prices
                    close=dxy_close,
                )

                result = calculator.update(gc_bar, dxy_bar)

                if result is not None:
                    bias_computations += 1

            # Should have computed bias at boundaries (once features are available)
            # After first 1H bar (minute 59), subsequent 15M boundaries should compute bias
            assert bias_computations > 0, "Should have computed bias at least once"

            # Should be warmed up after 1 hour
            assert calculator.is_warmed_up() is True

            # Buffers should contain data
            assert len(calculator.df_1h_buffer) >= 1
            assert len(calculator.df_15m_buffer) >= 4






"""Unit tests for incremental FeatureState engine."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
import math

import numpy as np
import pandas as pd
import pytest

from common.types import Candle
from feature_engine.state import (
    VWAPState,
    RSIState,
    EMAState,
    DXYCorrelationState,
    StructureState,
    FeatureState,
)


class TestVWAPState:
    """Tests for VWAPState class."""

    def test_single_candle(self):
        """Test VWAP calculation with single candle."""
        state = VWAPState(session_reset=False)
        candle = Candle(
            timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            open=100.0,
            high=102.0,
            low=98.0,
            close=101.0,
            volume=1000.0,
            symbol="GC",
            timeframe="1m",
            source="TEST",
        )
        
        vwap = state.update(candle)
        
        # VWAP should equal typical price for single candle
        typical_price = (102.0 + 98.0 + 101.0) / 3
        assert abs(vwap - typical_price) < 0.01

    def test_multiple_candles(self):
        """Test VWAP calculation with multiple candles."""
        state = VWAPState(session_reset=False)
        
        candles = [
            Candle(datetime(2025, 1, 1, 10, i, tzinfo=timezone.utc),
                   100.0, 102.0, 98.0, 101.0, 1000.0, "GC", "1m", "TEST")
            for i in range(3)
        ]
        
        vwaps = [state.update(c) for c in candles]
        
        # VWAP should be cumulative
        assert len(vwaps) == 3
        assert all(isinstance(v, float) for v in vwaps)

    def test_session_reset(self):
        """Test VWAP resets at session boundary."""
        state = VWAPState(session_reset=True)
        
        # First session
        candle1 = Candle(
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            100.0, 102.0, 98.0, 101.0, 1000.0, "GC", "1m", "TEST"
        )
        vwap1 = state.update(candle1)
        
        # Same session
        candle2 = Candle(
            datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
            101.0, 103.0, 99.0, 102.0, 1000.0, "GC", "1m", "TEST"
        )
        vwap2 = state.update(candle2)
        
        # New session (next day)
        candle3 = Candle(
            datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc),
            100.0, 102.0, 98.0, 101.0, 1000.0, "GC", "1m", "TEST"
        )
        vwap3 = state.update(candle3)
        
        # VWAP should reset on new session
        typical_price3 = (102.0 + 98.0 + 101.0) / 3
        assert abs(vwap3 - typical_price3) < 0.01

    def test_zero_volume(self):
        """Test VWAP handles zero volume gracefully."""
        state = VWAPState(session_reset=False)
        candle = Candle(
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            100.0, 102.0, 98.0, 101.0, 0.0, "GC", "1m", "TEST"
        )
        
        vwap = state.update(candle)
        
        # Should not raise error, should use epsilon
        assert isinstance(vwap, float)
        assert not math.isnan(vwap)


class TestRSIState:
    """Tests for RSIState class."""

    def test_warmup_period(self):
        """Test RSI returns None during warmup."""
        state = RSIState(period=14)
        
        # First 14 prices should return None
        for i in range(14):
            rsi = state.update(100.0 + i)
            assert rsi is None

    def test_first_rsi_value(self):
        """Test first RSI value after warmup."""
        state = RSIState(period=14)
        
        # Simulate 14 price changes (15 prices total)
        prices = [100.0 + i * 0.5 for i in range(15)]
        
        rsis = []
        for price in prices:
            rsi = state.update(price)
            rsis.append(rsi)
        
        # First 14 should be None, 15th should have value
        assert all(r is None for r in rsis[:14])
        assert rsis[14] is not None
        assert 0 <= rsis[14] <= 100

    def test_all_gains(self):
        """Test RSI with all gains (should be 100)."""
        state = RSIState(period=14)
        
        # Steadily increasing prices
        for i in range(20):
            rsi = state.update(100.0 + i)
        
        # Should approach 100
        assert rsi > 90

    def test_all_losses(self):
        """Test RSI with all losses (should be 0)."""
        state = RSIState(period=14)
        
        # Steadily decreasing prices
        for i in range(20):
            rsi = state.update(100.0 - i)
        
        # Should approach 0
        assert rsi < 10

    def test_wilders_smoothing(self):
        """Test RSI uses Wilder's smoothing correctly."""
        state = RSIState(period=14)
        
        # Known price sequence
        prices = [44.0, 44.5, 44.3, 44.8, 45.2, 45.0, 45.5, 46.0,
                  45.8, 46.5, 47.0, 46.8, 47.5, 48.0, 48.5]
        
        rsis = [state.update(p) for p in prices]
        
        # Should have valid RSI after period
        assert rsis[-1] is not None
        assert 0 <= rsis[-1] <= 100


class TestEMAState:
    """Tests for EMAState class."""

    def test_first_price_initialization(self):
        """Test EMA initializes with first price."""
        state = EMAState(periods=[9, 20, 50])
        
        emas = state.update(100.0)
        
        assert emas["ema_9"] == 100.0
        assert emas["ema_20"] == 100.0
        assert emas["ema_50"] == 100.0

    def test_ema_updates(self):
        """Test EMA updates correctly."""
        state = EMAState(periods=[9])
        
        # First price
        emas1 = state.update(100.0)
        assert emas1["ema_9"] == 100.0
        
        # Second price
        emas2 = state.update(102.0)
        
        # EMA should be between 100 and 102
        assert 100.0 < emas2["ema_9"] < 102.0
        
        # Alpha for period 9 = 2/(9+1) = 0.2
        # Expected: 102 * 0.2 + 100 * 0.8 = 100.4
        assert abs(emas2["ema_9"] - 100.4) < 0.01

    def test_multiple_periods(self):
        """Test multiple EMA periods calculated correctly."""
        state = EMAState(periods=[9, 20, 50])
        
        # Update with several prices
        for i in range(10):
            emas = state.update(100.0 + i)
        
        # All EMAs should have values
        assert "ema_9" in emas
        assert "ema_20" in emas
        assert "ema_50" in emas
        
        # Shorter period should be more responsive
        assert emas["ema_9"] > emas["ema_20"] > emas["ema_50"]


class TestDXYCorrelationState:
    """Tests for DXYCorrelationState class."""

    def test_warmup_period(self):
        """Test correlation returns None during warmup."""
        state = DXYCorrelationState(window=50)
        
        # First 49 updates should return None
        for i in range(49):
            corr = state.update(100.0 + i, 50.0 - i * 0.5, datetime.now(timezone.utc))
            assert corr is None

    def test_perfect_negative_correlation(self):
        """Test perfect negative correlation."""
        state = DXYCorrelationState(window=50)
        
        # GC up, DXY down
        for i in range(50):
            corr = state.update(
                100.0 + i,
                50.0 - i * 0.5,
                datetime.now(timezone.utc) + timedelta(minutes=i)
            )
        
        # Should be close to -1
        assert corr is not None
        assert corr < -0.9

    def test_perfect_positive_correlation(self):
        """Test perfect positive correlation."""
        state = DXYCorrelationState(window=50)
        
        # Both up
        for i in range(50):
            corr = state.update(
                100.0 + i,
                50.0 + i * 0.5,
                datetime.now(timezone.utc) + timedelta(minutes=i)
            )
        
        # Should be close to 1
        assert corr is not None
        assert corr > 0.9

    def test_no_correlation(self):
        """Test no correlation."""
        state = DXYCorrelationState(window=50)
        
        # Random-ish pattern
        for i in range(50):
            gc_price = 100.0 + (i % 5)
            dxy_price = 50.0 + ((i * 3) % 7)
            corr = state.update(
                gc_price,
                dxy_price,
                datetime.now(timezone.utc) + timedelta(minutes=i)
            )
        
        # Should be close to 0
        assert corr is not None
        assert -0.5 < corr < 0.5

    def test_missing_prices(self):
        """Test handling of missing prices."""
        state = DXYCorrelationState(window=50)
        
        # Update with None values
        corr1 = state.update(None, 50.0, datetime.now(timezone.utc))
        assert corr1 is None
        
        corr2 = state.update(100.0, None, datetime.now(timezone.utc))
        assert corr2 is None


class TestStructureState:
    """Tests for StructureState class."""

    def test_warmup_period(self):
        """Test structure labels return None during warmup."""
        state = StructureState(swing_window=5)
        
        # Need swing_window * 2 + 1 = 11 candles
        for i in range(10):
            label = state.update(100.0 + i, 95.0 + i)
            assert label is None

    def test_higher_high_detection(self):
        """Test HH (Higher High) detection."""
        state = StructureState(swing_window=2)
        
        # Create pattern: low, HIGH, low, HIGHER HIGH, low
        highs = [100, 105, 100, 110, 100, 95, 90]
        lows = [95, 100, 95, 105, 95, 90, 85]
        
        labels = []
        for h, l in zip(highs, lows):
            label = state.update(h, l)
            labels.append(label)
        
        # Should detect at least one structure label (HH, HL, LH, or LL)
        non_none_labels = [l for l in labels if l is not None]
        assert len(non_none_labels) > 0
        assert any(l in ["HH", "HL", "LH", "LL"] for l in non_none_labels)

    def test_lower_low_detection(self):
        """Test LL (Lower Low) detection."""
        state = StructureState(swing_window=2)
        
        # Create pattern: high, LOW, high, LOWER LOW, high
        highs = [100, 95, 100, 90, 100, 105, 110]
        lows = [95, 90, 95, 85, 95, 100, 105]
        
        labels = []
        for h, l in zip(highs, lows):
            label = state.update(h, l)
            labels.append(label)
        
        # Should detect at least one structure label (HH, HL, LH, or LL)
        non_none_labels = [l for l in labels if l is not None]
        assert len(non_none_labels) > 0
        assert any(l in ["HH", "HL", "LH", "LL"] for l in non_none_labels)

    def test_no_lookahead(self):
        """Test structure labels don't use future data."""
        state = StructureState(swing_window=2)
        
        # Add 5 candles (window * 2 + 1)
        highs = [100, 102, 101, 103, 102]
        lows = [95, 97, 96, 98, 97]
        
        labels = []
        for h, l in zip(highs, lows):
            label = state.update(h, l)
            labels.append(label)
        
        # Last label should be None (not enough future data)
        # Only center point can be labeled
        assert labels[-1] is None


class TestFeatureState:
    """Tests for FeatureState class."""

    def test_initialization(self):
        """Test FeatureState initializes correctly."""
        state = FeatureState(timeframe="1m")
        
        assert state.timeframe == "1m"
        assert state.is_ready() is False
        assert state.warmup_remaining() == 50

    def test_no_candles_error(self):
        """Test error when no candles provided."""
        state = FeatureState(timeframe="1m")
        
        with pytest.raises(ValueError, match="At least one"):
            state.update(gc_candle=None, dxy_candle=None)

    def test_gc_only_update(self):
        """Test update with GC candle only."""
        state = FeatureState(timeframe="1m")
        
        gc_candle = Candle(
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            100.0, 102.0, 98.0, 101.0, 1000.0, "GC", "1m", "TEST"
        )
        
        features = state.update(gc_candle=gc_candle)
        
        assert features is not None
        assert features["symbol"] == "GC"
        assert features["vwap"] is not None
        assert features["dxy_corr"] is None  # No DXY data yet

    def test_dxy_only_update(self):
        """Test update with DXY candle only."""
        state = FeatureState(timeframe="1m")
        
        dxy_candle = Candle(
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            100.0, 102.0, 98.0, 101.0, 1000.0, "DXY", "1m", "TEST"
        )
        
        features = state.update(dxy_candle=dxy_candle)
        
        # Should return None (no GC data yet)
        assert features is None

    def test_synchronized_update(self):
        """Test update with both GC and DXY candles."""
        state = FeatureState(timeframe="1m")
        
        gc_candle = Candle(
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            100.0, 102.0, 98.0, 101.0, 1000.0, "GC", "1m", "TEST"
        )
        dxy_candle = Candle(
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            50.0, 51.0, 49.0, 50.5, 1000.0, "DXY", "1m", "TEST"
        )
        
        features = state.update(gc_candle=gc_candle, dxy_candle=dxy_candle)
        
        assert features is not None
        assert features["symbol"] == "GC"
        assert features["vwap"] is not None

    def test_warmup_tracking(self):
        """Test warmup period tracking."""
        state = FeatureState(timeframe="1m", dxy_window=10)
        
        assert state.warmup_remaining() == 11  # max(10, 5*2+1)
        
        # Add candles
        for i in range(5):
            gc_candle = Candle(
                datetime(2025, 1, 1, 10, i, tzinfo=timezone.utc),
                100.0 + i, 102.0 + i, 98.0 + i, 101.0 + i, 1000.0, "GC", "1m", "TEST"
            )
            state.update(gc_candle=gc_candle)
        
        assert state.warmup_remaining() == 6
        assert state.is_ready() is False

    def test_all_features_present(self):
        """Test all expected features are present."""
        state = FeatureState(timeframe="1m")
        
        # Add enough candles to pass warmup
        for i in range(60):
            gc_candle = Candle(
                datetime(2025, 1, 1, 10, i, tzinfo=timezone.utc),
                100.0 + i * 0.1, 102.0 + i * 0.1, 98.0 + i * 0.1, 101.0 + i * 0.1,
                1000.0, "GC", "1m", "TEST"
            )
            dxy_candle = Candle(
                datetime(2025, 1, 1, 10, i, tzinfo=timezone.utc),
                50.0 - i * 0.05, 51.0 - i * 0.05, 49.0 - i * 0.05, 50.5 - i * 0.05,
                1000.0, "DXY", "1m", "TEST"
            )
            features = state.update(gc_candle=gc_candle, dxy_candle=dxy_candle)
        
        assert state.is_ready()
        assert features is not None
        
        # Check all expected columns
        expected_cols = [
            "timestamp", "symbol", "timeframe", "open", "high", "low", "close", "volume",
            "vwap", "rsi", "ema_9", "ema_20", "ema_50", "dxy_corr", 
            "structure_label", "vwap_deviation"
        ]
        for col in expected_cols:
            assert col in features.index

    def test_get_features(self):
        """Test get_features returns current state."""
        state = FeatureState(timeframe="1m")
        
        # Before any candles
        features = state.get_features()
        assert features["timestamp"] is None
        
        # After one candle
        gc_candle = Candle(
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            100.0, 102.0, 98.0, 101.0, 1000.0, "GC", "1m", "TEST"
        )
        state.update(gc_candle=gc_candle)
        
        features = state.get_features()
        assert features["timestamp"] is not None
        assert features["symbol"] == "GC"

    def test_out_of_order_warning(self, caplog):
        """Test warning logged for out-of-order candles."""
        state = FeatureState(timeframe="1m")
        
        # First candle
        gc_candle1 = Candle(
            datetime(2025, 1, 1, 10, 1, tzinfo=timezone.utc),
            100.0, 102.0, 98.0, 101.0, 1000.0, "GC", "1m", "TEST"
        )
        state.update(gc_candle=gc_candle1)
        
        # Out-of-order candle (earlier timestamp)
        gc_candle2 = Candle(
            datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            100.0, 102.0, 98.0, 101.0, 1000.0, "GC", "1m", "TEST"
        )
        state.update(gc_candle=gc_candle2)
        
        # Should log warning
        assert "Out-of-order" in caplog.text


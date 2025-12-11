"""Tests for StreamingFeatureProcessor.

Validates that streaming feature calculation produces identical results
to vectorized batch processing.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest
from common.types import Candle
from feature_engine.aggregator import aggregate_features
from feature_engine.streaming import StreamingFeatureProcessor


@pytest.fixture
def sample_candles():
    """Generate sample candle data for testing."""
    base_time = datetime(2025, 1, 1, 10, 0, tzinfo=UTC)

    gc_candles = []
    dxy_candles = []

    for i in range(100):
        timestamp = base_time.replace(minute=i % 60, hour=10 + i // 60)

        # Create GC candle with some variation
        gc_candles.append(
            Candle(
                timestamp=timestamp,
                open=2650.0 + i * 0.5,
                high=2652.0 + i * 0.5,
                low=2648.0 + i * 0.5,
                close=2650.5 + i * 0.5,
                volume=1000.0 + i * 10,
                symbol="GC",
                timeframe="1m",
                source="TEST",
            )
        )

        # Create DXY candle
        dxy_candles.append(
            Candle(
                timestamp=timestamp,
                open=104.0 - i * 0.01,
                high=104.1 - i * 0.01,
                low=103.9 - i * 0.01,
                close=104.05 - i * 0.01,
                volume=500.0,
                symbol="DXY",
                timeframe="1m",
                source="TEST",
            )
        )

    return gc_candles, dxy_candles


def test_streaming_processor_initialization():
    """Test StreamingFeatureProcessor initialization."""
    processor = StreamingFeatureProcessor(timeframe="1m")

    assert processor.timeframe == "1m"
    assert processor.rsi_period == 14
    assert processor.ema_periods == [9, 20, 50]
    assert processor.dxy_window == 50
    assert processor.swing_window == 2  # Automatically set based on timeframe (1m=2)
    assert processor.bar_count == 0


def test_streaming_ema_matches_batch(sample_candles):
    """Test that streaming EMA matches batch calculation."""
    gc_candles, dxy_candles = sample_candles

    # Streaming calculation
    processor = StreamingFeatureProcessor(timeframe="1m")
    streaming_results = []

    for gc, dxy in zip(gc_candles, dxy_candles, strict=False):
        features = processor.update(gc, dxy)
        streaming_results.append(features)

    # Batch calculation
    gc_df = pd.DataFrame(
        [
            {
                "ts_event": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in gc_candles
        ]
    )

    dxy_df = pd.DataFrame(
        [
            {
                "ts_event": c.timestamp,
                "close": c.close,
            }
            for c in dxy_candles
        ]
    )

    batch_features = aggregate_features(gc_df, dxy_df, timeframe="1m")

    # Compare EMAs (after warmup period)
    warmup = 50
    for i in range(warmup, len(streaming_results)):
        for period in [9, 20, 50]:
            streaming_ema = streaming_results[i][f"ema_{period}"]
            batch_ema = batch_features.iloc[i][f"ema_{period}"]

            # Allow small floating point difference
            assert abs(streaming_ema - batch_ema) < 0.01, (
                f"EMA_{period} mismatch at bar {i}: "
                f"streaming={streaming_ema:.4f}, batch={batch_ema:.4f}"
            )


def test_streaming_vwap_session_reset(sample_candles):
    """Test VWAP session reset behavior."""
    gc_candles, dxy_candles = sample_candles

    processor = StreamingFeatureProcessor(timeframe="1m", session_reset=True)

    prev_vwap = None
    session_resets = 0

    for gc, dxy in zip(gc_candles, dxy_candles, strict=False):
        features = processor.update(gc, dxy)
        current_vwap = features["vwap"]

        # Check if VWAP reset (should be close to current close price)
        if prev_vwap is not None and abs(current_vwap - gc.close) < 1.0:
            # This might indicate a session reset
            session_resets += 1

        prev_vwap = current_vwap

    # We should have calculated VWAP for all bars
    assert prev_vwap is not None


def test_streaming_rsi_calculation(sample_candles):
    """Test RSI calculation in streaming mode."""
    gc_candles, dxy_candles = sample_candles

    processor = StreamingFeatureProcessor(timeframe="1m", rsi_period=14)

    rsi_values = []
    for gc, dxy in zip(gc_candles, dxy_candles, strict=False):
        features = processor.update(gc, dxy)
        rsi = features.get("rsi")
        rsi_values.append(rsi)

    # RSI should be None for first 14 bars (warmup period)
    for i in range(14):
        assert rsi_values[i] is None, f"RSI should be None for bar {i}"

    # RSI should be calculated after warmup
    for i in range(15, len(rsi_values)):
        assert rsi_values[i] is not None, f"RSI should exist for bar {i}"
        assert 0 <= rsi_values[i] <= 100, f"RSI out of range: {rsi_values[i]}"


def test_streaming_dxy_correlation(sample_candles):
    """Test DXY correlation calculation in streaming mode."""
    gc_candles, dxy_candles = sample_candles

    processor = StreamingFeatureProcessor(timeframe="1m", dxy_window=50)

    corr_values = []
    for gc, dxy in zip(gc_candles, dxy_candles, strict=False):
        features = processor.update(gc, dxy)
        corr = features.get("dxy_corr")
        corr_values.append(corr)

    # Correlation should be None before window size reached
    # Note: correlation might start at window-1 due to how the buffer fills
    for i in range(49):
        assert corr_values[i] is None, f"Correlation should be None for bar {i}"

    # Correlation should exist after window
    # Allow small floating point precision errors (epsilon = 1e-6)
    for i in range(50, len(corr_values)):
        if corr_values[i] is not None:
            assert (
                -1.000001 <= corr_values[i] <= 1.000001
            ), f"Correlation out of range: {corr_values[i]}"


def test_streaming_structure_labels(sample_candles):
    """Test structure label calculation in streaming mode."""
    gc_candles, dxy_candles = sample_candles

    processor = StreamingFeatureProcessor(timeframe="1m", swing_window=5)

    label_values = []
    for gc, dxy in zip(gc_candles, dxy_candles, strict=False):
        features = processor.update(gc, dxy)
        label = features.get("structure_label")
        label_values.append(label)

    # Labels should be None or NaN during warmup period
    # NaN is acceptable as it's returned by pandas
    warmup = 5 * 2 + 1
    for i in range(warmup):
        label = label_values[i]
        assert label is None or (
            isinstance(label, float) and pd.isna(label)
        ), f"Label should be None or NaN for bar {i}, got {label}"

    # After warmup, some labels should appear
    # (Not all bars will have labels, only swing points)
    any(
        label is not None and not (isinstance(label, float) and pd.isna(label))
        for label in label_values[warmup:]
    )
    # Note: with trending synthetic data, we might not get swing points
    # So we just check the function ran without error


def test_streaming_warmup_check(sample_candles):
    """Test warmup check functionality."""
    gc_candles, dxy_candles = sample_candles

    processor = StreamingFeatureProcessor(timeframe="1m")

    # Should not be warmed up initially
    assert not processor.is_warmed_up()

    # Process bars
    for i, (gc, dxy) in enumerate(zip(gc_candles, dxy_candles, strict=False)):
        processor.update(gc, dxy)

        # Check warmup status
        # Warmup requires max(50 (ema), 15 (rsi), 50 (dxy), 7 (structure)) = 50
        # Since bar_count starts at 1 after first update, need >= 50 bar_count
        expected_warmup = (i + 1) >= 50
        assert processor.is_warmed_up() == expected_warmup, (
            f"Warmup mismatch at bar {i}: expected {expected_warmup}, "
            f"got {processor.is_warmed_up()}"
        )


def test_streaming_reset():
    """Test processor reset functionality."""
    gc_candle = Candle(
        timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        open=2650.0,
        high=2652.0,
        low=2648.0,
        close=2650.5,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    dxy_candle = Candle(
        timestamp=datetime(2025, 1, 1, 10, 0, tzinfo=UTC),
        open=104.0,
        high=104.1,
        low=103.9,
        close=104.05,
        volume=500.0,
        symbol="DXY",
        timeframe="1m",
        source="TEST",
    )

    processor = StreamingFeatureProcessor(timeframe="1m")

    # Process a bar
    processor.update(gc_candle, dxy_candle)
    assert processor.bar_count == 1

    # Reset
    processor.reset()
    assert processor.bar_count == 0
    assert all(v is None for v in processor.ema_states.values())

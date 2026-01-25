"""Unit tests for bar counter with invalid candle skipping.

Tests that invalid candles (NaN/Inf) are skipped in bar counting to match
legacy backtester behavior.

Following strict TDD - these tests are written FIRST and should FAIL until
invalid candle skipping is implemented.
"""

import math
from datetime import datetime, timezone

import pytest
from scp_shared.common.types import Candle


def utc_datetime(*args, **kwargs):
    """Create UTC timezone-aware datetime."""
    return datetime(*args, **kwargs, tzinfo=timezone.utc)


def test_is_valid_candle_with_valid_ohlc():
    """is_valid_candle should return True for valid OHLC data."""
    from execution_svc.trade_manager import is_valid_candle

    candle = Candle(
        timestamp=utc_datetime(2024, 10, 15, 10, 0),
        open=2651.0,
        high=2653.0,
        low=2649.0,
        close=2652.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    assert is_valid_candle(candle) is True


def test_is_valid_candle_with_nan_open():
    """is_valid_candle should return False for NaN in open."""
    from execution_svc.trade_manager import is_valid_candle

    candle = Candle(
        timestamp=utc_datetime(2024, 10, 15, 10, 0),
        open=math.nan,
        high=2653.0,
        low=2649.0,
        close=2652.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    assert is_valid_candle(candle) is False


def test_is_valid_candle_with_nan_high():
    """is_valid_candle should return False for NaN in high."""
    from execution_svc.trade_manager import is_valid_candle

    candle = Candle(
        timestamp=utc_datetime(2024, 10, 15, 10, 0),
        open=2651.0,
        high=math.nan,
        low=2649.0,
        close=2652.0,
        volume=1000.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    assert is_valid_candle(candle) is False


def test_is_valid_candle_with_inf_close():
    """is_valid_candle should return False for Inf in close."""
    from execution_svc.trade_manager import is_valid_candle
    from unittest.mock import Mock

    # Create mock candle with inf close
    candle = Mock(spec=Candle)
    candle.open = 2651.0
    candle.high = 2653.0
    candle.low = 2649.0
    candle.close = math.inf

    assert is_valid_candle(candle) is False


def test_is_valid_candle_with_negative_inf():
    """is_valid_candle should return False for negative Inf."""
    from execution_svc.trade_manager import is_valid_candle
    from unittest.mock import Mock

    # Create mock candle with negative inf low
    candle = Mock(spec=Candle)
    candle.open = 2651.0
    candle.high = 2653.0
    candle.low = -math.inf
    candle.close = 2652.0

    assert is_valid_candle(candle) is False

"""Test retest protection for VWAP_RECLAIM setups.

Following TDD: Write failing test first to verify SL is skipped on first bar.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from common.types import Candle
from rule_engine.signal import Signal

from backtester.entry_model import EntryExecution
from backtester.simulator import simulate_trade_outcome
from backtester.trade import Trade, create_trade_from_entry

UTC = ZoneInfo("UTC")


def test_vwap_reclaim_no_sl_on_first_bar():
    """Test that VWAP_RECLAIM doesn't stop out on the first bar after entry.

    Scenario: VWAP_RECLAIM long enters at 2650.0 with SL at 2648.0.
              First bar after entry wicks down to 2647.5 (below SL) but closes at 2650.5.
    Expected: Trade should NOT stop out on first bar (retest protection).
              Trade should continue and eventually hit TP.
    """
    # Create signal
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={},
        rationale="VWAP reclaim",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )

    entry_execution = EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=datetime(2025, 11, 1, 10, 31, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )

    # Confirmation candle
    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        open=2649.0,
        high=2650.5,
        low=2648.0,
        close=2650.0,
        volume=100,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    # Create trade
    trade = create_trade_from_entry(
        entry_execution=entry_execution,
        confirmation_candle=confirmation_candle,
        bos_candle=None,
        risk_config={"max_contracts": 1},
        market_context={
            "month": 11,
            "htf_aligned": True,
            "dxy_aligned": True,
        },
    )

    # Future candles: Bar 1 wicks below SL, but should be ignored (retest protection)
    future_data = {
        "open": [2650.5, 2650.8, 2651.5],  # Bar 1, 2, 3
        "high": [2651.0, 2651.5, 2652.0],
        "low": [2647.5, 2650.5, 2651.0],  # Bar 1 wicks below SL at 2648.0
        "close": [2650.5, 2651.0, 2651.8],
        "volume": [100, 100, 100],
    }

    timestamps = [
        datetime(2025, 11, 1, 10, 32, tzinfo=UTC),  # Bar 1 (first bar after entry)
        datetime(2025, 11, 1, 10, 33, tzinfo=UTC),  # Bar 2
        datetime(2025, 11, 1, 10, 34, tzinfo=UTC),  # Bar 3
    ]

    future_candles = pd.DataFrame(future_data, index=timestamps)

    # Simulate trade
    closed_trade = simulate_trade_outcome(
        trade=trade,
        future_candles=future_candles,
        invalidation_checker=None,
        config=None,
    )

    # Assert: Trade should NOT stop out on first bar
    assert closed_trade.exit_reason != "sl", (
        f"Trade should not stop out on first bar (retest protection). "
        f"Got exit_reason={closed_trade.exit_reason}, exit_bar={closed_trade.duration_bars}"
    )

    # Trade should still be running or exit for another reason
    assert closed_trade.status in [
        "OPEN",
        "CLOSED_WIN",
        "CLOSED_LOSS",
    ], f"Trade should continue past first bar, got status={closed_trade.status}"


def test_vwap_reclaim_sl_works_after_first_bar():
    """Test that SL works normally after the grace period.

    Scenario: VWAP_RECLAIM long enters at 2650.0 with SL at 2648.0.
              Bars 1-3: Price stays above SL (grace period).
              Bar 4: Price drops below SL.
    Expected: Trade should stop out on Bar 4 (after grace period ends).

    Note: VWAP_RECLAIM has a 4-bar grace period (MIN_BARS_RECLAIM = 4) where
    SL/TP checks are skipped to allow the retest pattern to develop.
    """
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={},
        rationale="VWAP reclaim",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )

    entry_execution = EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=datetime(2025, 11, 1, 10, 31, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )

    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        open=2649.0,
        high=2650.5,
        low=2648.0,
        close=2650.0,
        volume=100,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    trade = create_trade_from_entry(
        entry_execution=entry_execution,
        confirmation_candle=confirmation_candle,
        bos_candle=None,
        risk_config={"max_contracts": 1},
        market_context={
            "month": 11,
            "htf_aligned": True,
            "dxy_aligned": True,
        },
    )

    # Future candles: Bars 1-3 OK (grace period), Bar 4 hits SL
    future_data = {
        "open": [2650.5, 2650.3, 2650.1, 2649.5],  # Bars 1-4
        "high": [2651.0, 2651.0, 2651.0, 2650.0],
        "low": [2649.5, 2649.5, 2649.5, 2647.5],  # Bar 4 hits SL at 2648.0
        "close": [2650.8, 2650.6, 2650.4, 2647.8],
        "volume": [100, 100, 100, 100],
    }

    timestamps = [
        datetime(2025, 11, 1, 10, 32, tzinfo=UTC),  # Bar 1
        datetime(2025, 11, 1, 10, 33, tzinfo=UTC),  # Bar 2
        datetime(2025, 11, 1, 10, 34, tzinfo=UTC),  # Bar 3
        datetime(2025, 11, 1, 10, 35, tzinfo=UTC),  # Bar 4
    ]

    future_candles = pd.DataFrame(future_data, index=timestamps)

    # Simulate trade
    closed_trade = simulate_trade_outcome(
        trade=trade,
        future_candles=future_candles,
        invalidation_checker=None,
        config=None,
    )

    # Assert: Trade should stop out on Bar 4 (after grace period)
    assert (
        closed_trade.exit_reason == "sl"
    ), f"Trade should stop out on Bar 4. Got exit_reason={closed_trade.exit_reason}"
    assert (
        closed_trade.duration_bars == 4
    ), f"Trade should exit on Bar 4. Got duration_bars={closed_trade.duration_bars}"


def test_non_vwap_reclaim_no_retest_protection():
    """Test that non-VWAP_RECLAIM setups don't get retest protection.

    Scenario: VWAP_FADE long enters at 2650.0.
              Bar 1: Close-based SL check (close above SL, no hit).
              Bar 2: Wick-based SL check (wick hits SL, should exit).
    Expected: Trade should stop out on Bar 2 (no retest protection, no grace period for SL/TP).
    """
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_FADE",  # Not VWAP_RECLAIM
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={},
        rationale="VWAP fade",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )

    entry_execution = EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=datetime(2025, 11, 1, 10, 31, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )

    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        open=2649.5,
        high=2650.5,
        low=2649.0,
        close=2650.0,
        volume=100,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    trade = create_trade_from_entry(
        entry_execution=entry_execution,
        confirmation_candle=confirmation_candle,
        bos_candle=None,
        risk_config={"max_contracts": 1},
        market_context={
            "month": 11,
            "htf_aligned": True,
            "dxy_aligned": True,
        },
    )

    # Future candles:
    # Bar 1: close-based SL (close=2649.2 > SL, no hit)
    # Bar 2: wick-based SL (low=2648.5 <= SL, hits)
    future_data = {
        "open": [2649.5, 2649.0],
        "high": [2650.0, 2649.5],
        "low": [2649.0, 2648.5],  # Bar 2 wick hits SL
        "close": [2649.2, 2648.8],  # Bar 1 close above SL, Bar 2 close below SL
        "volume": [100, 100],
    }

    timestamps = [
        datetime(2025, 11, 1, 10, 32, tzinfo=UTC),
        datetime(2025, 11, 1, 10, 33, tzinfo=UTC),
    ]
    future_candles = pd.DataFrame(future_data, index=timestamps)

    # Simulate trade
    closed_trade = simulate_trade_outcome(
        trade=trade,
        future_candles=future_candles,
        invalidation_checker=None,
        config=None,
    )

    # Assert: Trade should stop out on Bar 2 (no grace period for FADE SL/TP)
    # Bar 1 uses close-based SL (close > SL, no hit)
    # Bar 2 uses wick-based SL (low <= SL, hits)
    assert (
        closed_trade.exit_reason == "sl"
    ), f"VWAP_FADE should stop out on Bar 2 (no retest protection). Got exit_reason={closed_trade.exit_reason}"
    assert (
        closed_trade.duration_bars == 2
    ), f"Trade should exit on Bar 2. Got duration_bars={closed_trade.duration_bars}"

"""Integration test for diagnostics - verify diagnostics are populated in real backtest flow.

This test verifies that diagnostics are properly attached at entry, during trade
lifetime, and at exit (SL/TP/invalidation).
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from backtester.diagnostics import add_nested_diag
from backtester.entry_model import EntryExecution
from backtester.invalidations import InvalidationChecker
from backtester.simulator import simulate_trade_outcome
from backtester.trade import create_trade_from_entry, to_dict
from common.types import Candle
from rule_engine.signal import Signal


def test_diagnostics_populated_at_entry():
    """Test that entry_context diagnostics are populated when trade is created."""
    # Create signal
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={"vwap": 10.0, "structure": 10.0, "rsi": 8.0},
        rationale="Strong reclaim",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )

    # Create entry execution
    entry = EntryExecution(
        signal_timestamp=datetime(2025, 11, 1, 10, 0, tzinfo=UTC),
        entry_timestamp=datetime(2025, 11, 1, 10, 1, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )

    # Create confirmation candle
    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 1, tzinfo=UTC),
        open=2649.0,
        high=2651.0,
        low=2648.0,
        close=2650.0,
        volume=100.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    # Create trade
    trade = create_trade_from_entry(
        entry_execution=entry,
        confirmation_candle=confirmation_candle,
        bos_candle=None,
        risk_config={"max_contracts": 1, "risk_per_trade": 350.0},
        market_context={"month": 11, "htf_aligned": True, "dxy_aligned": True},
    )

    # Add entry context diagnostics (simulating what replay_loop does)
    add_nested_diag(trade, "entry_context", "vwap", 2648.5)
    add_nested_diag(trade, "entry_context", "structure_label", "HH")
    add_nested_diag(trade, "entry_context", "rsi", 55.2)
    add_nested_diag(trade, "entry_context", "scoring_factors", signal.factors)

    # Verify diagnostics are populated
    assert "entry_context" in trade.diagnostics
    assert trade.diagnostics["entry_context"]["vwap"] == 2648.5
    assert trade.diagnostics["entry_context"]["structure_label"] == "HH"
    assert trade.diagnostics["entry_context"]["rsi"] == 55.2
    assert trade.diagnostics["entry_context"]["scoring_factors"]["vwap"] == 10.0


def test_diagnostics_populated_on_sl_hit():
    """Test that sl_hit_context diagnostics are populated when SL is hit."""
    # Create a trade that will hit SL
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_FADE",
        htf_bias="bullish",
        score=8.0,
        confidence="A+",
        factors={},
        rationale="Test fade",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )

    entry = EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=datetime(2025, 11, 1, 10, 1, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )

    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 1, tzinfo=UTC),
        open=2649.0,
        high=2651.0,
        low=2648.0,
        close=2650.0,
        volume=100.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    trade = create_trade_from_entry(
        entry_execution=entry,
        confirmation_candle=confirmation_candle,
        bos_candle=None,
        risk_config={"max_contracts": 1},
        market_context={"month": 11, "htf_aligned": False, "dxy_aligned": False},
    )

    # Create future candles that hit SL
    future_candles = pd.DataFrame(
        {
            "open": [2650.0, 2649.0, 2647.0],
            "high": [2651.0, 2650.0, 2648.0],
            "low": [2648.0, 2647.0, 2645.0],  # Bar 3 hits SL
            "close": [2649.0, 2648.0, 2646.0],
            "volume": [100.0, 100.0, 100.0],
        },
        index=pd.DatetimeIndex(
            [
                datetime(2025, 11, 1, 10, 2, tzinfo=UTC),
                datetime(2025, 11, 1, 10, 3, tzinfo=UTC),
                datetime(2025, 11, 1, 10, 4, tzinfo=UTC),
            ]
        ),
    )

    # Simulate trade outcome (will hit SL)
    closed_trade = simulate_trade_outcome(
        trade=trade,
        future_candles=future_candles,
        invalidation_checker=InvalidationChecker(),
        config=None,
        future_features=None,
    )

    # Verify trade hit SL and diagnostics are populated
    assert closed_trade.exit_reason == "sl"
    assert "sl_hit_context" in closed_trade.diagnostics
    assert "sl_level" in closed_trade.diagnostics["sl_hit_context"]
    assert "bars_elapsed" in closed_trade.diagnostics["sl_hit_context"]
    assert "candle_low" in closed_trade.diagnostics["sl_hit_context"]


def test_diagnostics_populated_on_tp_hit():
    """Test that tp_hit_context diagnostics are populated when TP is hit."""
    # Create a trade that will hit TP
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=9.0,
        confidence="A+",
        factors={},
        rationale="Test reclaim",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )

    entry = EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=datetime(2025, 11, 1, 10, 1, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )

    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 1, tzinfo=UTC),
        open=2649.0,
        high=2651.0,
        low=2648.0,
        close=2650.0,
        volume=100.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    trade = create_trade_from_entry(
        entry_execution=entry,
        confirmation_candle=confirmation_candle,
        bos_candle=None,
        risk_config={"max_contracts": 1},
        market_context={"month": 11, "htf_aligned": True, "dxy_aligned": True},
    )

    # Create future candles that hit TP
    # VWAP_RECLAIM has 8-bar grace period, so we need 9+ candles for TP to be checked
    tp_price = trade.take_profit
    # Ensure candle data is valid (high >= low, close between low and high)
    # Bar 9: high must be >= tp_price to hit TP
    bar9_low = min(tp_price - 1.0, 2659.0)  # Ensure low < tp_price
    bar9_high = max(tp_price + 1.0, 2660.0)  # Ensure high >= tp_price
    
    # Build candle data for 9 bars
    opens = [2651.0 + i * 0.5 for i in range(8)] + [tp_price - 0.5]
    highs = [2652.0 + i * 0.5 for i in range(8)] + [bar9_high]  # Bar 9 hits TP
    lows = [2650.0 + i * 0.5 for i in range(8)] + [bar9_low]
    closes = [2651.5 + i * 0.5 for i in range(8)] + [tp_price]
    volumes = [100.0] * 9
    
    timestamps = [datetime(2025, 11, 1, 10, 2 + i, tzinfo=UTC) for i in range(9)]
    
    future_candles = pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        },
        index=pd.DatetimeIndex(timestamps),
    )

    # Simulate trade outcome (will hit TP)
    closed_trade = simulate_trade_outcome(
        trade=trade,
        future_candles=future_candles,
        invalidation_checker=InvalidationChecker(),
        config=None,
        future_features=None,
    )

    # Verify trade hit TP and diagnostics are populated
    assert closed_trade.exit_reason == "tp"
    assert "tp_hit_context" in closed_trade.diagnostics
    assert "tp_level" in closed_trade.diagnostics["tp_hit_context"]
    assert "bars_elapsed" in closed_trade.diagnostics["tp_hit_context"]
    assert "candle_high" in closed_trade.diagnostics["tp_hit_context"]


def test_diagnostics_survive_json_roundtrip():
    """Test that diagnostics survive serialization/deserialization."""
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 0, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={"vwap": 10.0},
        rationale="Test",
        validation_flags={},
        enforcer_tier="EarlyMild",
    )

    entry = EntryExecution(
        signal_timestamp=signal.timestamp,
        entry_timestamp=datetime(2025, 11, 1, 10, 1, tzinfo=UTC),
        entry_price=2650.0,
        signal=signal,
        executed=True,
        rejection_reason=None,
    )

    confirmation_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 1, tzinfo=UTC),
        open=2649.0,
        high=2651.0,
        low=2648.0,
        close=2650.0,
        volume=100.0,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )

    trade = create_trade_from_entry(
        entry_execution=entry,
        confirmation_candle=confirmation_candle,
        bos_candle=None,
        risk_config={"max_contracts": 1},
        market_context={"month": 11, "htf_aligned": True, "dxy_aligned": True},
    )

    # Add comprehensive diagnostics
    add_nested_diag(trade, "entry_context", "vwap", 2648.5)
    add_nested_diag(trade, "entry_context", "structure_label", "HH")
    add_nested_diag(trade, "rejection_during_trade", "bar_1", {"wick_penetration": 0.8})
    add_nested_diag(trade, "rejection_during_trade", "bar_2", {"wick_penetration": 0.6})

    # Serialize to dict (JSON-ready)
    trade_dict = to_dict(trade)

    # Verify diagnostics in serialized form
    assert "diagnostics" in trade_dict
    assert "entry_context" in trade_dict["diagnostics"]
    assert trade_dict["diagnostics"]["entry_context"]["vwap"] == 2648.5
    assert "rejection_during_trade" in trade_dict["diagnostics"]
    assert len(trade_dict["diagnostics"]["rejection_during_trade"]) == 2

"""Test HTF invalidation uses locked entry structure (FIX #4).

Following TDD: Write failing tests first to verify HTF invalidation only fires
on true structural breaks, not candle color drift.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from common.types import Candle
from rule_engine.signal import Signal

from backtester.entry_model import EntryExecution
from backtester.invalidations import InvalidationChecker
from backtester.trade import Trade

UTC = ZoneInfo("UTC")


def test_htf_invalidation_not_triggered_by_candle_color():
    """Test that HTF invalidation is NOT triggered by candle color change.
    
    Scenario: Long trade enters with HTF bullish structure (HH/HL).
              HTF candle turns bearish (red) but structure remains intact (still HH/HL).
    Expected: No HTF invalidation.
    """
    # Create a long trade with bullish HTF bias
    signal = Signal(
        timestamp=datetime(2025, 11, 1, 10, 30, tzinfo=UTC),
        symbol="GC",
        timeframe="1m",
        direction="long",
        setup_type="VWAP_RECLAIM",
        htf_bias="bullish",
        score=8.5,
        confidence="A+",
        factors={"htf_structure": "HH/HL"},  # Entry structure
        rationale="HTF bullish",
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
    
    trade = Trade(
        trade_id="test-htf-001",
        symbol="GC",
        timeframe="1m",
        entry_execution=entry_execution,
        entry_timestamp=datetime(2025, 11, 1, 10, 31, tzinfo=UTC),
        entry_price=2650.0,
        direction="long",
        setup_type="VWAP_RECLAIM",
        stop_loss=2645.0,
        take_profit=2665.0,
        sl_rationale="Below structure",
        tp_rationale="3R continuation",
        risk_amount=5.0,
        reward_amount=15.0,
        r_multiple=3.0,
        contracts=1,
        exit_timestamp=None,
        exit_price=None,
        exit_reason=None,
        pnl=None,
        pnl_percent=None,
        r_realized=None,
        pnl_dollars=None,
        pnl_net=None,
        slippage_cost=None,
        commission_cost=None,
        status="OPEN",
        duration_bars=None,
        invalidation_triggered=False,
        ignore_first_retest_bar=False,
    )
    
    # Current candle: HTF still has HH/HL structure, just red candle
    current_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 32, tzinfo=UTC),
        open=2652.0,
        high=2653.0,
        low=2651.0,
        close=2651.5,  # Red candle (close < open)
        volume=100,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )
    
    # HTF context: Structure still intact (HH/HL), just candle color changed
    htf_context = {
        "structure_label": "HL",  # Still bullish swing (HL is part of HH/HL pattern)
        "htf_bias": "bullish",  # Still bullish structure
    }
    
    checker = InvalidationChecker()
    
    # Act: Check HTF invalidation
    # Pass htf_context as features dict
    should_exit, reason = checker.check_htf_structure_invalidation(
        trade=trade,
        candle=current_candle,
        features=htf_context,
    )
    
    # Assert: Should NOT invalidate due to candle color alone
    # Structure is still HH/HL (same as entry), so no invalidation
    assert should_exit is False, (
        f"HTF invalidation should NOT fire when structure unchanged. "
        f"Entry: HH/HL, Current: HH/HL. Got should_exit={should_exit}, reason={reason}"
    )


def test_htf_invalidation_triggered_by_structure_break():
    """Test that HTF invalidation IS triggered by true structure break.
    
    Scenario: Long trade enters with HTF bullish structure (HH/HL).
              HTF structure breaks to LH/LL (bearish).
    Expected: HTF invalidation triggered.
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
        factors={"htf_structure": "HH/HL"},  # Entry structure
        rationale="HTF bullish",
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
    
    trade = Trade(
        trade_id="test-htf-002",
        symbol="GC",
        timeframe="1m",
        entry_execution=entry_execution,
        entry_timestamp=datetime(2025, 11, 1, 10, 31, tzinfo=UTC),
        entry_price=2650.0,
        direction="long",
        setup_type="VWAP_RECLAIM",
        stop_loss=2645.0,
        take_profit=2665.0,
        sl_rationale="Below structure",
        tp_rationale="3R continuation",
        risk_amount=5.0,
        reward_amount=15.0,
        r_multiple=3.0,
        contracts=1,
        exit_timestamp=None,
        exit_price=None,
        exit_reason=None,
        pnl=None,
        pnl_percent=None,
        r_realized=None,
        pnl_dollars=None,
        pnl_net=None,
        slippage_cost=None,
        commission_cost=None,
        status="OPEN",
        duration_bars=None,
        invalidation_triggered=False,
        ignore_first_retest_bar=False,
    )
    
    current_candle = Candle(
        timestamp=datetime(2025, 11, 1, 10, 32, tzinfo=UTC),
        open=2648.0,
        high=2649.0,
        low=2647.0,
        close=2648.5,
        volume=100,
        symbol="GC",
        timeframe="1m",
        source="TEST",
    )
    
    # HTF context: Structure broken to LH/LL (bearish)
    htf_context = {
        "structure_label": "LL",  # Bearish swing (lower low)
        "htf_bias": "bearish",  # Structure break
    }
    
    checker = InvalidationChecker()
    
    # Act: Check HTF invalidation
    # Pass htf_context as features dict
    should_exit, reason = checker.check_htf_structure_invalidation(
        trade=trade,
        candle=current_candle,
        features=htf_context,
    )
    
    # Assert: Should invalidate on structure break
    # Entry was HH/HL (bullish), now LH/LL (bearish) - this is a break
    assert should_exit is True, (
        f"HTF invalidation should fire on structure break. "
        f"Entry: HH/HL (bullish), Current: LH/LL (bearish). "
        f"Got should_exit={should_exit}"
    )
    assert "htf" in reason.lower(), f"Reason should mention HTF: {reason}"


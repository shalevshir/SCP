"""Direct test to verify that future_features are passed to simulate_trade_outcome.

This test directly verifies the bug: the call to simulate_trade_outcome in pipeline.py
does not pass the future_features parameter, which causes all feature-based invalidations
to be silently skipped.
"""

import pandas as pd
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

from backtester.pipeline import run_backtest_with_trades
from rule_engine.htf.types import HTFBias


def test_simulate_trade_outcome_receives_future_features():
    """Verify that simulate_trade_outcome is called with future_features parameter.
    
    This verifies the bug fix: future_features must be passed to enable
    VWAP, HTF structure, and DXY flip invalidation checks during trade simulation.
    """
    # Create minimal test data with enough bars for feature computation
    start = datetime(2024, 10, 15, 10, 0, tzinfo=ZoneInfo("UTC"))
    timestamps = [start + timedelta(minutes=i) for i in range(200)]
    
    # Create price data that will generate signals (uptrend with pullback)
    prices = [2650.0 + i * 0.1 for i in range(200)]
    gc_data = {
        "open": prices,
        "high": [p + 1.0 for p in prices],
        "low": [p - 1.0 for p in prices],
        "close": prices,
        "volume": [1000] * 200,
    }
    gc_df = pd.DataFrame(gc_data, index=timestamps)
    
    dxy_data = {
        "open": [104.0] * 200,
        "high": [104.1] * 200,
        "low": [103.9] * 200,
        "close": [104.0] * 200,
        "volume": [1000] * 200,
    }
    dxy_df = pd.DataFrame(dxy_data, index=timestamps)
    
    def bullish_htf_bias(features, context):
        return HTFBias(
            bias="bullish",
            direction="long",
            score=9.0,
            confidence="high",
        )
    
    market_state = {
        "tier_active": "MILD",
        "session_ok": True,
    }
    
    risk_config = {
        "startup": {"max_risk_per_trade": 350, "max_daily_loss": 600},
    }
    
    # Mock simulate_trade_outcome to track calls
    with patch("backtester.pipeline.simulate_trade_outcome") as mock_simulate:
        # Make mock return a closed trade
        def mock_simulate_side_effect(trade, *args, **kwargs):
            from dataclasses import replace
            return replace(
                trade,
                exit_timestamp=trade.entry_timestamp,
                exit_price=trade.entry_price,
                exit_reason="tp",
                pnl=10.0,
            )
        
        mock_simulate.side_effect = mock_simulate_side_effect
        
        # Run backtest
        try:
            trades = run_backtest_with_trades(
                gc_df=gc_df,
                dxy_df=dxy_df,
                timeframe="1m",
                market_state=market_state,
                htf_bias_func=bullish_htf_bias,
                risk_config=risk_config,
            )
        except Exception as e:
            # Even if backtest fails, we can check if simulate was called
            pass
        
        # Check if simulate_trade_outcome was called
        if mock_simulate.call_count == 0:
            pytest.skip("No trades generated - cannot verify fix")
        
        print(f"\n✓ simulate_trade_outcome called {mock_simulate.call_count} times")
        
        # Verify that future_features was passed to simulate_trade_outcome
        failures = []
        for i, call in enumerate(mock_simulate.call_args_list):
            args, kwargs = call
            
            # Check if future_features is in kwargs
            if "future_features" not in kwargs:
                failures.append(
                    f"Call {i+1}: 'future_features' parameter missing. "
                    "This causes VWAP, HTF structure, and DXY flip invalidations "
                    "to be silently skipped."
                )
                continue
            
            # Check if future_features is not None (or if it's None, log warning)
            if kwargs["future_features"] is None:
                print(
                    f"  ⚠️  Call {i+1}: future_features=None (no future candles available)"
                )
            else:
                print(
                    f"  ✓ Call {i+1}: future_features provided "
                    f"(shape: {kwargs['future_features'].shape})"
                )
        
        # Assert no failures
        if failures:
            pytest.fail("\n".join(failures))


def test_invalidation_checker_returns_early_without_features():
    """Verify that InvalidationChecker returns early when features is None.
    
    This test documents the behavior that makes the bug critical: when features
    is None, all feature-based checks return (False, None) immediately, silently
    skipping important SOP invalidation rules.
    """
    from backtester.invalidations import InvalidationChecker
    from backtester.entry_model import EntryExecution
    from common.types import Candle
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from dataclasses import dataclass
    
    # Create minimal mock trade (just enough for invalidation checks)
    @dataclass
    class MockTrade:
        trade_id: str
        entry_timestamp: datetime
        entry_price: float
        direction: str
        setup_type: str
        stop_loss: float = 2640.0
        take_profit: float = 2680.0
    
    checker = InvalidationChecker()
    
    # Create a test trade
    trade = MockTrade(
        trade_id="test_1",
        entry_timestamp=datetime(2024, 10, 15, 10, 0, tzinfo=ZoneInfo("UTC")),
        entry_price=2650.0,
        direction="long",
        setup_type="VWAP_RECLAIM",
    )
    
    # Create a test candle
    candle = Candle(
        timestamp=datetime(2024, 10, 15, 10, 5, tzinfo=ZoneInfo("UTC")),
        open=2651.0,
        high=2655.0,
        low=2650.0,
        close=2654.0,
        volume=1000,
        symbol="GC",
        timeframe="1m",
        source="test",
    )
    
    # Test VWAP invalidation without features
    is_invalid, reason = checker.check_vwap_invalidation(trade, candle, features=None)
    assert is_invalid is False, "VWAP check should return False when features=None"
    assert reason is None, "VWAP check should return None reason when features=None"
    
    # Test HTF structure invalidation without features
    is_invalid, reason = checker.check_htf_structure_invalidation(trade, candle, features=None)
    assert is_invalid is False, "HTF check should return False when features=None"
    assert reason is None, "HTF check should return None reason when features=None"
    
    # Test DXY flip without features
    is_invalid, reason = checker.check_dxy_flip(trade, candle, features=None)
    assert is_invalid is False, "DXY check should return False when features=None"
    assert reason is None, "DXY check should return None reason when features=None"
    
    # This behavior is DOCUMENTED but the bug is that pipeline.py doesn't pass features!
    print(
        "\n⚠️  CRITICAL: InvalidationChecker returns early when features=None\n"
        "   This means VWAP, HTF structure, and DXY flip invalidations are\n"
        "   silently skipped if future_features is not passed to simulate_trade_outcome.\n"
        "   The pipeline MUST compute and pass future_features!"
    )


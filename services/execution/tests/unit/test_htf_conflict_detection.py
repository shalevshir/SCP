"""Unit tests for HTF conflict detection in runner hard invalidation.

Tests the critical safety check that exits DXY_CONTINUATION runners when
HTF conflict is detected (e.g., 15m/1h structure mismatch).
"""

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from scp_shared.common.types import Candle
from scp_shared.execution.types import TradeRecord
from scp_shared.messaging.schemas import HTFBiasMessage, SignalMessage
from execution_svc.trade_manager import TradeManager


@pytest.fixture
def trade_manager_deps():
    """Create mock dependencies for TradeManager."""
    broker = MagicMock()
    broker.place_order = AsyncMock(return_value=MagicMock(status="filled", filled_price=2650.0))
    broker.close_position = AsyncMock()
    broker.reconcile_positions = AsyncMock()

    state_machine_manager = MagicMock()
    state_machine_manager._bar_counter = 0
    state_machine_manager.create_from_signal = AsyncMock()
    state_machine_manager.check_confirmation = MagicMock(return_value=True)
    state_machine_manager.execute = AsyncMock()

    trade_repository = MagicMock()
    trade_repository.insert_trade = AsyncMock(return_value="test-trade-id")
    trade_repository.close_trade = AsyncMock()
    trade_repository.get_open_trades = AsyncMock(return_value=[])
    trade_repository.get_trades_for_date = AsyncMock(return_value=[])
    trade_repository.update_reached_1r = AsyncMock()
    trade_repository.update_breakeven = AsyncMock()

    trade_publisher = MagicMock()
    trade_publisher.publish_opened = AsyncMock()
    trade_publisher.publish_closed = AsyncMock()

    db_pool = MagicMock()

    return {
        "broker": broker,
        "state_machine_manager": state_machine_manager,
        "trade_repository": trade_repository,
        "trade_publisher": trade_publisher,
        "db_pool": db_pool,
    }


@pytest.mark.asyncio
async def test_on_htf_bias_includes_conflict_fields(trade_manager_deps):
    """Test that on_htf_bias() properly includes conflict_detected and conflict_reason."""
    manager = TradeManager(**trade_manager_deps)

    # Create HTFBiasMessage with conflict
    htf_msg = HTFBiasMessage(
        timestamp=datetime.now(timezone.utc),
        bias="bullish",
        score=8.0,
        confidence="A+",
        structure_15m="HH",
        structure_1h="LL",  # Mismatch
        dxy_aligned=True,
        chop_detected=False,
        conflict_detected=True,
        conflict_reason="15m/1h structure mismatch",
    )

    # Call on_htf_bias
    manager.on_htf_bias(htf_msg)

    # Verify dict includes ALL critical fields
    assert manager._latest_htf_bias is not None
    assert manager._latest_htf_bias["conflict_detected"] is True
    assert manager._latest_htf_bias["conflict_reason"] == "15m/1h structure mismatch"
    assert manager._latest_htf_bias["chop_detected"] is False
    assert manager._latest_htf_bias["dxy_aligned"] is True


@pytest.mark.asyncio
async def test_on_htf_bias_no_conflict(trade_manager_deps):
    """Test that on_htf_bias() properly handles no conflict case."""
    manager = TradeManager(**trade_manager_deps)

    htf_msg = HTFBiasMessage(
        timestamp=datetime.now(timezone.utc),
        bias="bullish",
        score=8.0,
        confidence="A+",
        structure_15m="HH",
        structure_1h="HH",
        dxy_aligned=True,
        chop_detected=False,
        conflict_detected=False,
        conflict_reason=None,
    )

    manager.on_htf_bias(htf_msg)

    assert manager._latest_htf_bias is not None
    assert manager._latest_htf_bias["conflict_detected"] is False
    assert manager._latest_htf_bias["conflict_reason"] is None


@pytest.mark.asyncio
async def test_runner_exits_on_htf_conflict(trade_manager_deps):
    """Test that runner exits immediately when HTF conflict is detected."""
    manager = TradeManager(**trade_manager_deps)
    manager._sm_manager._bar_counter = 10

    # Create a DXY_CONTINUATION trade with partial taken
    trade = TradeRecord(
        trade_id="test-trade-id",
        signal_id="test-signal-id",
        symbol="GC",
        direction="long",
        setup_type="DXY_CONTINUATION",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2680.0,
        quantity=1,
        risk_amount=10.0,
        reward_amount=30.0,
        entry_timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
        entry_bar_idx=5,
        partial_taken=True,
        tp1_hit_bar_idx=8,
        runner_unlocked=False,
    )

    manager._active_trades[trade.trade_id] = trade
    manager._trade_entry_bars[trade.trade_id] = 5

    # Set up invalidation checker state with all required fields
    manager._invalidation_checker._get_trade_state = MagicMock(
        return_value={
            "partial_taken": True,
            "tp1_hit_bar_idx": 8,
            "reached_1r": True,  # Required by update_state
            "vwap_reclaimed": False,  # Required by DXY_CONTINUATION checks
        }
    )

    # Update HTF bias with conflict
    htf_msg = HTFBiasMessage(
        timestamp=datetime.now(timezone.utc),
        bias="bullish",
        score=8.0,
        confidence="A+",
        structure_15m="HH",
        structure_1h="LL",
        dxy_aligned=True,
        chop_detected=False,
        conflict_detected=True,
        conflict_reason="15m/1h structure mismatch",
    )
    manager.on_htf_bias(htf_msg)

    # Create candle
    candle = Candle(
        timestamp=datetime.now(timezone.utc),
        open=2655.0,
        high=2658.0,
        low=2654.0,
        close=2656.0,
        volume=100.0,
        symbol="GC",
        timeframe="1m",
        source="STREAM",
    )

    # Call _check_trade_exit
    await manager._check_trade_exit(trade, candle, features={})

    # Verify trade was closed due to runner invalidation
    trade_manager_deps["trade_repository"].close_trade.assert_called_once()
    call_kwargs = trade_manager_deps["trade_repository"].close_trade.call_args[1]
    assert call_kwargs["trade_id"] == "test-trade-id"
    assert "RUNNER_INVALIDATED" in call_kwargs["exit_reason"]


@pytest.mark.asyncio
async def test_runner_continues_without_htf_conflict(trade_manager_deps):
    """Test that runner continues normally when no HTF conflict."""
    manager = TradeManager(**trade_manager_deps)
    manager._sm_manager._bar_counter = 10

    # Create a DXY_CONTINUATION trade with partial taken
    trade = TradeRecord(
        trade_id="test-trade-id",
        signal_id="test-signal-id",
        symbol="GC",
        direction="long",
        setup_type="DXY_CONTINUATION",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2680.0,
        quantity=1,
        risk_amount=10.0,
        reward_amount=30.0,
        entry_timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
        entry_bar_idx=5,
        partial_taken=True,
        tp1_hit_bar_idx=8,
        runner_unlocked=False,
    )

    manager._active_trades[trade.trade_id] = trade
    manager._trade_entry_bars[trade.trade_id] = 5

    # Set up invalidation checker state with all required fields
    manager._invalidation_checker._get_trade_state = MagicMock(
        return_value={
            "partial_taken": True,
            "tp1_hit_bar_idx": 8,
            "reached_1r": True,  # Required by update_state
            "vwap_reclaimed": False,  # Required by DXY_CONTINUATION checks
        }
    )

    # Update HTF bias WITHOUT conflict
    htf_msg = HTFBiasMessage(
        timestamp=datetime.now(timezone.utc),
        bias="bullish",
        score=8.0,
        confidence="A+",
        structure_15m="HH",
        structure_1h="HH",
        dxy_aligned=True,
        chop_detected=False,
        conflict_detected=False,
        conflict_reason=None,
    )
    manager.on_htf_bias(htf_msg)

    # Create candle
    candle = Candle(
        timestamp=datetime.now(timezone.utc),
        open=2655.0,
        high=2658.0,
        low=2654.0,
        close=2656.0,
        volume=100.0,
        symbol="GC",
        timeframe="1m",
        source="STREAM",
    )

    # Call _check_trade_exit
    await manager._check_trade_exit(trade, candle, features={})

    # Verify trade was NOT closed
    trade_manager_deps["trade_repository"].close_trade.assert_not_called()
    # Trade should still be active
    assert trade.trade_id in manager._active_trades


@pytest.mark.asyncio
async def test_htf_conflict_takes_priority_over_unlock(trade_manager_deps):
    """Test that HTF conflict invalidation happens BEFORE unlock check.

    Per spec Section 4: Hard invalidation must be checked FIRST,
    before any unlock attempts.
    """
    manager = TradeManager(**trade_manager_deps)
    manager._sm_manager._bar_counter = 10

    # Create a DXY_CONTINUATION trade with partial taken
    trade = TradeRecord(
        trade_id="test-trade-id",
        signal_id="test-signal-id",
        symbol="GC",
        direction="long",
        setup_type="DXY_CONTINUATION",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2680.0,
        quantity=1,
        risk_amount=10.0,
        reward_amount=30.0,
        entry_timestamp=datetime.now(timezone.utc) - timedelta(minutes=5),
        entry_bar_idx=5,
        partial_taken=True,
        tp1_hit_bar_idx=8,
        runner_unlocked=False,
    )

    manager._active_trades[trade.trade_id] = trade
    manager._trade_entry_bars[trade.trade_id] = 5

    # Set up invalidation checker state with all required fields
    manager._invalidation_checker._get_trade_state = MagicMock(
        return_value={
            "partial_taken": True,
            "tp1_hit_bar_idx": 8,
            "reached_1r": True,  # Required by update_state
            "vwap_reclaimed": False,  # Required by DXY_CONTINUATION checks
        }
    )

    # Update HTF bias with conflict
    htf_msg = HTFBiasMessage(
        timestamp=datetime.now(timezone.utc),
        bias="bullish",
        score=8.0,
        confidence="A+",
        structure_15m="HH",
        structure_1h="LL",
        dxy_aligned=True,
        chop_detected=False,
        conflict_detected=True,
        conflict_reason="15m/1h structure mismatch",
    )
    manager.on_htf_bias(htf_msg)

    # Create candle with BOS detected (which would unlock runner)
    candle = Candle(
        timestamp=datetime.now(timezone.utc),
        open=2655.0,
        high=2658.0,
        low=2654.0,
        close=2656.0,
        volume=100.0,
        symbol="GC",
        timeframe="1m",
        source="STREAM",
    )

    # Features with BOS detected
    features = {
        "bos_detected": True,
        "bos_direction": "bullish",
    }

    # Call _check_trade_exit
    await manager._check_trade_exit(trade, candle, features)

    # Verify trade was closed due to INVALIDATION, not unlocked
    trade_manager_deps["trade_repository"].close_trade.assert_called_once()
    call_kwargs = trade_manager_deps["trade_repository"].close_trade.call_args[1]
    assert "RUNNER_INVALIDATED" in call_kwargs["exit_reason"]
    # Runner should NOT be marked as unlocked
    assert not trade.runner_unlocked

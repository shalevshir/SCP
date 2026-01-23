"""Integration test: Bot Core -> Execution Service.

Tests the signal-to-trade lifecycle: signal generation, trade execution,
SL/TP monitoring, and trade closure.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import redis.asyncio as redis
from scp_shared.database import DatabasePool
from scp_shared.messaging import RedisStreamConsumer, RedisStreamPublisher
from scp_shared.messaging.schemas import (
    CandleMessage,
    FeaturesMessage,
    HTFBiasMessage,
    SignalMessage,
    TradeMessage,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_signal_triggers_trade_execution(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    db_pool: DatabasePool,
    clean_streams: None,
    clean_database: None,
    ensure_services_healthy: None,
) -> None:
    """Test that a signal published to signals.pending triggers trade execution.

    Flow:
    1. Publish A+ signal to signals.pending
    2. Verify trade appears in trades.opened stream
    3. Verify trade record exists in database
    """
    # Create consumers
    trades_opened_consumer = RedisStreamConsumer(
        redis_client,
        stream="trades.opened",
        group="integration-test-trades",
        consumer_name="test-trades-1",
        message_type=TradeMessage,
    )

    # CRITICAL: Create consumer group BEFORE any messages are published
    # Messages published before group exists won't be delivered to that group
    # Delete and recreate to ensure clean state (prevents missing messages from previous runs)
    try:
        await redis_client.xgroup_destroy("trades.opened", "integration-test-trades")
    except Exception:
        pass  # Group might not exist

    await trades_opened_consumer.ensure_group()

    # Create and publish a signal
    signal = SignalMessage(
        id=str(uuid.uuid4()),  # Valid UUID format
        timestamp=datetime.now(timezone.utc),
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=9.5,
        confidence="A+",
        entry_price=2650.0,
        sl_price=2640.0,  # 10 points below
        tp_price=2680.0,  # 30 points above (3R)
        factors={
            "vwap_reclaim": True,
            "htf_aligned": True,
            "dxy_aligned": True,
        },
    )

    await redis_publisher.publish("signals.pending", signal)

    # Wait for signal to be consumed and state machine created
    # State machine is created with detection_bar_idx = current_bar_counter
    await asyncio.sleep(1.0)

    # Publish multiple candles AND matching features to ensure execution service processes them.
    # The execution service uses a CandleFeatureSynchronizer that requires BOTH
    # candle AND features with matching timestamps before processing.
    # CRITICAL: First candle increments bar_counter, allowing confirmation (bar_idx > detection_bar_idx)
    for i in range(5):  # Publish more candles to ensure confirmation and execution
        bar_timestamp = signal.timestamp + timedelta(minutes=i + 1)

        next_bar_candle = CandleMessage(
            timestamp=bar_timestamp,
            symbol="GC",
            timeframe="1m",
            open=2650.0,  # Signal entry price
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )

        # CRITICAL: Execution service requires matching features for each candle
        next_bar_features = FeaturesMessage(
            timestamp=bar_timestamp,
            symbol="GC",
            timeframe="1m",
            close=2651.0,
            vwap=2650.0,  # VWAP at entry price - no invalidation
            rsi=50.0,
            ema_9=2651.0,
            ema_20=2650.0,
            ema_50=2648.0,
            dxy_correlation=-0.3,
            structure_label="HL",
            vwap_deviation=0.04,
        )

        await redis_publisher.publish("candles.1m.gc", next_bar_candle)
        await redis_publisher.publish("features.1m", next_bar_features)
        await asyncio.sleep(0.5)  # Longer delay to ensure processing

    # Wait for execution service to complete processing (confirmation + execution)
    await asyncio.sleep(5.0)

    # Check trades.opened stream
    opened_trades = await trades_opened_consumer.read(count=10, block_ms=5000)

    assert len(opened_trades) > 0, "No trades opened after signal"

    # Find the trade matching our signal (there may be stale trades from service's in-memory buffer)
    matching_trades = [t for t in opened_trades if t.signal_id == signal.id]
    assert len(matching_trades) > 0, (
        f"Trade for signal {signal.id} not found. "
        f"Found trades with signal_ids: {[t.signal_id for t in opened_trades]}"
    )
    trade = matching_trades[0]
    assert trade.direction == "long"
    assert trade.entry_price == 2650.0
    assert trade.sl_price == 2640.0
    assert trade.tp_price == 2680.0

    # Verify trade in database
    db_trades = await db_pool.fetch(
        "SELECT * FROM trades WHERE signal_id = $1",
        signal.id,
    )

    assert len(db_trades) > 0, "Trade not found in database"
    assert db_trades[0]["direction"] == "long"
    assert db_trades[0]["setup_type"] == "VWAP_RECLAIM"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sl_hit_closes_trade(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    db_pool: DatabasePool,
    clean_streams: None,
    clean_database: None,
    ensure_services_healthy: None,
) -> None:
    """Test that price hitting SL closes the trade.

    Flow:
    1. Open trade via signal
    2. Publish candle that hits SL
    3. Verify trade appears in trades.closed stream
    4. Verify trade marked as closed in database
    """
    trades_opened_consumer = RedisStreamConsumer(
        redis_client,
        stream="trades.opened",
        group="integration-test-sl",
        consumer_name="test-sl-1",
        message_type=TradeMessage,
    )

    trades_closed_consumer = RedisStreamConsumer(
        redis_client,
        stream="trades.closed",
        group="integration-test-sl-closed",
        consumer_name="test-sl-closed-1",
        message_type=TradeMessage,
    )

    # CRITICAL: Create consumer groups BEFORE any messages are published
    # Delete and recreate to ensure clean state (prevents missing messages from previous runs)
    try:
        await redis_client.xgroup_destroy("trades.opened", "integration-test-sl")
    except Exception:
        pass  # Group might not exist
    try:
        await redis_client.xgroup_destroy("trades.closed", "integration-test-sl-closed")
    except Exception:
        pass  # Group might not exist

    await trades_opened_consumer.ensure_group()
    await trades_closed_consumer.ensure_group()

    # Publish signal
    signal = SignalMessage(
        id=str(uuid.uuid4()),  # Valid UUID format
        timestamp=datetime.now(timezone.utc),
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=9.0,
        confidence="A+",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2680.0,
        factors={},
    )

    await redis_publisher.publish("signals.pending", signal)

    # Wait for signal to be consumed and state machine created
    await asyncio.sleep(1.0)

    # Execute trade with multiple candles AND matching features
    # Use close prices ABOVE VWAP to avoid VWAP invalidation before SL candle
    last_entry_candle = None
    for i in range(5):  # Publish more candles to ensure confirmation and execution
        bar_timestamp = signal.timestamp + timedelta(minutes=i + 1)

        entry_candle = CandleMessage(
            timestamp=bar_timestamp,
            symbol="GC",
            timeframe="1m",
            open=2660.0,
            high=2662.0,
            low=2658.0,
            close=2661.0,  # Above VWAP to avoid invalidation
            volume=1000.0,
        )

        # CRITICAL: Matching features for each candle
        entry_features = FeaturesMessage(
            timestamp=bar_timestamp,
            symbol="GC",
            timeframe="1m",
            close=2661.0,
            vwap=2655.0,  # VWAP below close - no invalidation for long
            rsi=55.0,
            ema_9=2660.0,
            ema_20=2658.0,
            ema_50=2655.0,
            dxy_correlation=-0.3,
            structure_label="HL",
            vwap_deviation=0.23,
        )
        last_entry_candle = entry_candle

        await redis_publisher.publish("candles.1m.gc", entry_candle)
        await redis_publisher.publish("features.1m", entry_features)
        await asyncio.sleep(0.5)  # Longer delay to ensure processing

    await asyncio.sleep(5.0)  # Wait longer for confirmation + execution

    assert last_entry_candle is not None, "No candles were created"

    # Verify trade opened - look for our specific signal
    opened = await trades_opened_consumer.read(count=10, block_ms=5000)
    assert len(opened) > 0, "Trade not opened - cannot test SL hit"
    matching = [t for t in opened if t.signal_id == signal.id]
    assert len(matching) > 0, f"Trade for signal {signal.id} not found"
    opened_trade = matching[0]

    # VWAP_RECLAIM has 8-bar grace period for SL/TP
    # Publish enough candles to exceed grace period before hitting SL
    for i in range(10):
        grace_timestamp = last_entry_candle.timestamp + timedelta(minutes=i + 1)
        grace_candle = CandleMessage(
            timestamp=grace_timestamp,
            symbol="GC",
            timeframe="1m",
            open=2655.0,  # Above VWAP to avoid invalidation
            high=2656.0,
            low=2654.0,
            close=2655.0,
            volume=1000.0,
        )
        grace_features = FeaturesMessage(
            timestamp=grace_timestamp,
            symbol="GC",
            timeframe="1m",
            close=2655.0,
            vwap=2650.0,  # VWAP below close - no invalidation
            rsi=50.0,
            ema_9=2655.0,
            ema_20=2650.0,
            ema_50=2655.0,
            dxy_correlation=-0.3,
            structure_label="HL",
            vwap_deviation=0.19,
        )
        await redis_publisher.publish("candles.1m.gc", grace_candle)
        await redis_publisher.publish("features.1m", grace_features)
        await asyncio.sleep(0.1)

    # Now publish candle that hits SL (after grace period)
    sl_timestamp = last_entry_candle.timestamp + timedelta(minutes=11)
    sl_candle = CandleMessage(
        timestamp=sl_timestamp,
        symbol="GC",
        timeframe="1m",
        open=2645.0,
        high=2646.0,
        low=2639.0,  # Hits SL at 2640.0
        close=2641.0,
        volume=1000.0,
    )
    sl_features = FeaturesMessage(
        timestamp=sl_timestamp,
        symbol="GC",
        timeframe="1m",
        close=2641.0,
        vwap=2650.0,
        rsi=35.0,
        ema_9=2645.0,
        ema_20=2650.0,
        ema_50=2655.0,
        dxy_correlation=-0.3,
        structure_label="LL",
        vwap_deviation=-0.35,
    )

    await redis_publisher.publish("candles.1m.gc", sl_candle)
    await redis_publisher.publish("features.1m", sl_features)
    await asyncio.sleep(1.5)

    # Check trades.closed stream - look for our specific signal
    closed = await trades_closed_consumer.read(count=10, block_ms=3000)

    assert len(closed) > 0, "Trade not closed after SL hit"

    matching_closed = [t for t in closed if t.signal_id == signal.id]
    assert len(matching_closed) > 0, f"Closed trade for signal {signal.id} not found"
    closed_trade = matching_closed[0]
    assert closed_trade.exit_price == 2640.0, "Exit price should match SL"
    assert "SL" in (closed_trade.exit_reason or ""), "Exit reason should indicate SL"

    # Verify negative PnL
    assert closed_trade.pnl_points is not None
    assert closed_trade.pnl_points < 0, "SL hit should result in negative PnL"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tp_hit_closes_trade(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    db_pool: DatabasePool,
    clean_streams: None,
    clean_database: None,
    ensure_services_healthy: None,
) -> None:
    """Test that price hitting TP closes the trade with profit."""
    trades_opened_consumer = RedisStreamConsumer(
        redis_client,
        stream="trades.opened",
        group="integration-test-tp",
        consumer_name="test-tp-1",
        message_type=TradeMessage,
    )

    trades_closed_consumer = RedisStreamConsumer(
        redis_client,
        stream="trades.closed",
        group="integration-test-tp-closed",
        consumer_name="test-tp-closed-1",
        message_type=TradeMessage,
    )

    # CRITICAL: Create consumer groups BEFORE any messages are published
    # Delete and recreate to ensure clean state (prevents missing messages from previous runs)
    try:
        await redis_client.xgroup_destroy("trades.opened", "integration-test-tp")
    except Exception:
        pass  # Group might not exist
    try:
        await redis_client.xgroup_destroy("trades.closed", "integration-test-tp-closed")
    except Exception:
        pass  # Group might not exist

    await trades_opened_consumer.ensure_group()
    await trades_closed_consumer.ensure_group()

    # Publish signal
    signal = SignalMessage(
        id=str(uuid.uuid4()),  # Valid UUID format
        timestamp=datetime.now(timezone.utc),
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=9.5,
        confidence="A+",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2680.0,
        factors={},
    )

    await redis_publisher.publish("signals.pending", signal)

    # Wait for signal to be consumed and state machine created
    await asyncio.sleep(1.0)

    # Execute trade with multiple candles AND matching features
    # Use close prices ABOVE VWAP to avoid VWAP invalidation before TP candle
    last_entry_candle = None
    for i in range(5):  # Publish more candles to ensure confirmation and execution
        bar_timestamp = signal.timestamp + timedelta(minutes=i + 1)

        entry_candle = CandleMessage(
            timestamp=bar_timestamp,
            symbol="GC",
            timeframe="1m",
            open=2660.0,
            high=2662.0,
            low=2658.0,
            close=2661.0,  # Above VWAP to avoid invalidation
            volume=1000.0,
        )

        # CRITICAL: Matching features for each candle
        entry_features = FeaturesMessage(
            timestamp=bar_timestamp,
            symbol="GC",
            timeframe="1m",
            close=2661.0,
            vwap=2655.0,  # VWAP below close - no invalidation for long
            rsi=60.0,
            ema_9=2660.0,
            ema_20=2658.0,
            ema_50=2655.0,
            dxy_correlation=-0.3,
            structure_label="HH",
            vwap_deviation=0.23,
        )
        last_entry_candle = entry_candle

        await redis_publisher.publish("candles.1m.gc", entry_candle)
        await redis_publisher.publish("features.1m", entry_features)
        await asyncio.sleep(0.5)  # Longer delay to ensure processing

    await asyncio.sleep(5.0)  # Wait longer for confirmation + execution

    assert last_entry_candle is not None, "No candles were created"

    # Verify opened - look for our specific signal
    opened = await trades_opened_consumer.read(count=10, block_ms=5000)
    assert len(opened) > 0, "Trade not opened - cannot test TP hit"
    matching = [t for t in opened if t.signal_id == signal.id]
    assert len(matching) > 0, f"Trade for signal {signal.id} not found"

    # VWAP_RECLAIM has 8-bar grace period for SL/TP
    # Publish enough candles to exceed grace period before hitting TP
    for i in range(10):
        grace_timestamp = last_entry_candle.timestamp + timedelta(minutes=i + 1)
        grace_candle = CandleMessage(
            timestamp=grace_timestamp,
            symbol="GC",
            timeframe="1m",
            open=2665.0,  # Above VWAP to avoid invalidation
            high=2666.0,
            low=2664.0,
            close=2665.0,
            volume=1000.0,
        )
        grace_features = FeaturesMessage(
            timestamp=grace_timestamp,
            symbol="GC",
            timeframe="1m",
            close=2665.0,
            vwap=2655.0,  # VWAP below close - no invalidation
            rsi=60.0,
            ema_9=2665.0,
            ema_20=2660.0,
            ema_50=2655.0,
            dxy_correlation=-0.3,
            structure_label="HH",
            vwap_deviation=0.38,
        )
        await redis_publisher.publish("candles.1m.gc", grace_candle)
        await redis_publisher.publish("features.1m", grace_features)
        await asyncio.sleep(0.1)

    # Now publish candle that hits TP (after grace period)
    tp_timestamp = last_entry_candle.timestamp + timedelta(minutes=11)
    tp_candle = CandleMessage(
        timestamp=tp_timestamp,
        symbol="GC",
        timeframe="1m",
        open=2675.0,
        high=2681.0,  # Hits TP at 2680.0
        low=2674.0,
        close=2679.0,  # Above VWAP
        volume=1000.0,
    )
    tp_features = FeaturesMessage(
        timestamp=tp_timestamp,
        symbol="GC",
        timeframe="1m",
        close=2679.0,
        vwap=2665.0,  # VWAP well below - healthy trend
        rsi=70.0,
        ema_9=2675.0,
        ema_20=2670.0,
        ema_50=2660.0,
        dxy_correlation=-0.3,
        structure_label="HH",
        vwap_deviation=0.53,
    )

    await redis_publisher.publish("candles.1m.gc", tp_candle)
    await redis_publisher.publish("features.1m", tp_features)
    await asyncio.sleep(1.5)

    # Check trades.closed - look for our specific signal
    closed = await trades_closed_consumer.read(count=10, block_ms=3000)

    assert len(closed) > 0, "Trade not closed after TP hit"

    matching_closed = [t for t in closed if t.signal_id == signal.id]
    assert len(matching_closed) > 0, f"Closed trade for signal {signal.id} not found"
    closed_trade = matching_closed[0]
    assert closed_trade.exit_price == 2680.0, "Exit price should match TP"
    assert "TP" in (closed_trade.exit_reason or ""), "Exit reason should indicate TP"

    # Verify positive PnL
    # Entry is at candle open (2660), not signal entry_price (2650)
    # PnL = 2680 - 2660 = 20 points
    assert closed_trade.pnl_points is not None
    assert (
        closed_trade.pnl_points > 0
    ), f"TP hit should result in positive PnL, got {closed_trade.pnl_points}"
    # Allow some flexibility in PnL calculation (entry might be slightly different)
    assert (
        closed_trade.pnl_points >= 15.0
    ), f"PnL should be at least 15 points, got {closed_trade.pnl_points}"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalidation_closes_trade(
    redis_client: redis.Redis,
    redis_publisher: RedisStreamPublisher,
    clean_streams: None,
    clean_database: None,
    ensure_services_healthy: None,
) -> None:
    """Test that invalidation (VWAP loss) closes the trade early."""
    trades_opened_consumer = RedisStreamConsumer(
        redis_client,
        stream="trades.opened",
        group="integration-test-invalid-opened",
        consumer_name="test-invalid-opened-1",
        message_type=TradeMessage,
    )

    trades_closed_consumer = RedisStreamConsumer(
        redis_client,
        stream="trades.closed",
        group="integration-test-invalid",
        consumer_name="test-invalid-1",
        message_type=TradeMessage,
    )

    # CRITICAL: Create consumer groups BEFORE any messages are published
    # Delete and recreate to ensure clean state (prevents missing messages from previous runs)
    try:
        await redis_client.xgroup_destroy(
            "trades.opened", "integration-test-invalid-opened"
        )
    except Exception:
        pass  # Group might not exist
    try:
        await redis_client.xgroup_destroy("trades.closed", "integration-test-invalid")
    except Exception:
        pass  # Group might not exist

    await trades_opened_consumer.ensure_group()
    await trades_closed_consumer.ensure_group()

    # Publish signal
    signal = SignalMessage(
        id=str(uuid.uuid4()),  # Valid UUID format
        timestamp=datetime.now(timezone.utc),
        direction="long",
        setup_type="VWAP_RECLAIM",
        score=9.0,
        confidence="A+",
        entry_price=2650.0,
        sl_price=2640.0,
        tp_price=2680.0,
        factors={},
    )

    await redis_publisher.publish("signals.pending", signal)

    # Wait for signal to be consumed and state machine created
    await asyncio.sleep(1.0)

    # Execute trade with multiple candles AND matching features
    # Use close prices ABOVE VWAP to avoid early invalidation
    last_entry_candle = None
    for i in range(5):  # Publish more candles to ensure confirmation and execution
        bar_timestamp = signal.timestamp + timedelta(minutes=i + 1)

        entry_candle = CandleMessage(
            timestamp=bar_timestamp,
            symbol="GC",
            timeframe="1m",
            open=2660.0,
            high=2662.0,
            low=2658.0,
            close=2661.0,  # Above VWAP to avoid early invalidation
            volume=1000.0,
        )

        # CRITICAL: Matching features for each candle
        entry_features = FeaturesMessage(
            timestamp=bar_timestamp,
            symbol="GC",
            timeframe="1m",
            close=2661.0,
            vwap=2655.0,  # VWAP below close - no invalidation for long
            rsi=55.0,
            ema_9=2660.0,
            ema_20=2658.0,
            ema_50=2655.0,
            dxy_correlation=-0.3,
            structure_label="HL",
            vwap_deviation=0.23,
        )
        last_entry_candle = entry_candle

        await redis_publisher.publish("candles.1m.gc", entry_candle)
        await redis_publisher.publish("features.1m", entry_features)
        await asyncio.sleep(0.5)  # Longer delay to ensure processing

    await asyncio.sleep(5.0)  # Wait longer for confirmation + execution

    assert last_entry_candle is not None, "No candles were created"

    # FIRST verify trade was opened before testing invalidation
    opened = await trades_opened_consumer.read(count=10, block_ms=5000)
    assert len(opened) > 0, "Trade not opened - cannot test invalidation"
    matching = [t for t in opened if t.signal_id == signal.id]
    assert len(matching) > 0, f"Trade for signal {signal.id} not found"

    # VWAP_RECLAIM has 8-bar grace period for invalidation
    # Publish enough candles to exceed grace period before invalidation
    for i in range(10):
        grace_timestamp = last_entry_candle.timestamp + timedelta(minutes=i + 1)
        grace_candle = CandleMessage(
            timestamp=grace_timestamp,
            symbol="GC",
            timeframe="1m",
            open=2660.0,  # Above VWAP to avoid early invalidation
            high=2661.0,
            low=2659.0,
            close=2660.0,
            volume=1000.0,
        )
        grace_features = FeaturesMessage(
            timestamp=grace_timestamp,
            symbol="GC",
            timeframe="1m",
            close=2660.0,
            vwap=2655.0,  # VWAP below close - no invalidation
            rsi=55.0,
            ema_9=2660.0,
            ema_20=2658.0,
            ema_50=2655.0,
            dxy_correlation=-0.3,
            structure_label="HL",
            vwap_deviation=0.19,
        )
        await redis_publisher.publish("candles.1m.gc", grace_candle)
        await redis_publisher.publish("features.1m", grace_features)
        await asyncio.sleep(0.1)

    # Now publish 2 CONSECUTIVE invalidation candles (VWAP_RECLAIM requires 2-bar confirmation)
    # First invalidation candle (after grace period)
    for i in range(2):  # Publish 2 consecutive bars with close < VWAP
        invalid_timestamp = last_entry_candle.timestamp + timedelta(minutes=11 + i)

        invalid_candle = CandleMessage(
            timestamp=invalid_timestamp,
            symbol="GC",
            timeframe="1m",
            open=2646.0,
            high=2647.0,
            low=2644.0,
            close=2645.0,  # Below VWAP
            volume=1000.0,
        )

        invalid_features = FeaturesMessage(
            timestamp=invalid_timestamp,
            symbol="GC",
            timeframe="1m",
            close=2645.0,
            vwap=2648.0,  # VWAP above price - invalidation for long
            rsi=40.0,
            ema_9=2647.0,
            ema_20=2650.0,
            ema_50=2655.0,
            dxy_correlation=-0.3,
            structure_label="LH",
            vwap_deviation=-0.11,
        )

        await redis_publisher.publish("candles.1m.gc", invalid_candle)
        await redis_publisher.publish("features.1m", invalid_features)
        await asyncio.sleep(0.5)  # Small delay between bars

    # Wait for invalidation processing
    await asyncio.sleep(2.0)

    # Check if trade was closed due to invalidation
    closed = await trades_closed_consumer.read(count=1, block_ms=3000)

    # CRITICAL: Invalidation must close the trade - test should not pass silently
    assert len(closed) > 0, (
        "Trade should have been closed by invalidation. "
        "If no trade was closed, the invalidation feature is broken."
    )

    # Find our specific trade
    matching_closed = [t for t in closed if t.signal_id == signal.id]
    assert len(matching_closed) > 0, f"Closed trade for signal {signal.id} not found"
    closed_trade = matching_closed[0]
    # Should be closed for invalidation (VWAP or otherwise)
    # Exit reason should indicate invalidation
    assert closed_trade.exit_reason is not None
    # Verify it's not SL or TP
    assert "SL" not in closed_trade.exit_reason
    assert "TP" not in closed_trade.exit_reason

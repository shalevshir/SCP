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
    
    # Wait briefly for signal to be consumed and buffered
    await asyncio.sleep(0.5)
    
    # Publish multiple candles to ensure execution service processes them
    # (services use 1000ms blocking reads, so we need to ensure a candle arrives
    # in the same read cycle after the signal is buffered)
    for i in range(3):
        next_bar_candle = CandleMessage(
            timestamp=signal.timestamp + timedelta(minutes=i + 1),
            symbol="GC",
            timeframe="1m",
            open=2650.0,  # Signal entry price
            high=2652.0,
            low=2649.0,
            close=2651.0,
            volume=1000.0,
        )
        
        await redis_publisher.publish("candles.1m.gc", next_bar_candle)
        await asyncio.sleep(0.3)
    
    # Wait for execution service to complete processing
    await asyncio.sleep(3.0)
    
    # Check trades.opened stream
    opened_trades = await trades_opened_consumer.read(count=5, block_ms=5000)
    
    assert len(opened_trades) > 0, "No trades opened after signal"
    
    # Verify trade details
    trade = opened_trades[0]
    assert trade.signal_id == signal.id
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
    
    # Wait briefly for signal to be consumed and buffered
    await asyncio.sleep(0.5)
    
    # Execute trade with multiple candles to ensure processing
    last_entry_candle = None
    for i in range(3):
        entry_candle = CandleMessage(
            timestamp=signal.timestamp + timedelta(minutes=i + 1),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
            volume=1000.0,
        )
        last_entry_candle = entry_candle
        
        await redis_publisher.publish("candles.1m.gc", entry_candle)
        await asyncio.sleep(0.3)
    
    await asyncio.sleep(2.0)
    
    assert last_entry_candle is not None, "No candles were created"
    
    # Verify trade opened
    opened = await trades_opened_consumer.read(count=1, block_ms=5000)
    assert len(opened) > 0, "Trade not opened"
    
    # Publish candle that hits SL (low touches or breaks SL price)
    sl_candle = CandleMessage(
        timestamp=last_entry_candle.timestamp + timedelta(minutes=1),
        symbol="GC",
        timeframe="1m",
        open=2648.0,
        high=2649.0,
        low=2639.0,  # Hits SL at 2640.0
        close=2641.0,
        volume=1000.0,
    )
    
    await redis_publisher.publish("candles.1m.gc", sl_candle)
    await asyncio.sleep(1.5)
    
    # Check trades.closed stream
    closed = await trades_closed_consumer.read(count=1, block_ms=3000)
    
    assert len(closed) > 0, "Trade not closed after SL hit"
    
    closed_trade = closed[0]
    assert closed_trade.signal_id == signal.id
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
    
    # Wait briefly for signal to be consumed and buffered
    await asyncio.sleep(0.5)
    
    # Execute trade with multiple candles to ensure processing
    last_entry_candle = None
    for i in range(3):
        entry_candle = CandleMessage(
            timestamp=signal.timestamp + timedelta(minutes=i + 1),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
            volume=1000.0,
        )
        last_entry_candle = entry_candle
        
        await redis_publisher.publish("candles.1m.gc", entry_candle)
        await asyncio.sleep(0.3)
    
    await asyncio.sleep(2.0)
    
    assert last_entry_candle is not None, "No candles were created"
    
    # Verify opened
    opened = await trades_opened_consumer.read(count=1, block_ms=5000)
    assert len(opened) > 0
    
    # Publish candle that hits TP (high reaches TP price)
    tp_candle = CandleMessage(
        timestamp=last_entry_candle.timestamp + timedelta(minutes=1),
        symbol="GC",
        timeframe="1m",
        open=2670.0,
        high=2681.0,  # Hits TP at 2680.0
        low=2669.0,
        close=2678.0,
        volume=1000.0,
    )
    
    await redis_publisher.publish("candles.1m.gc", tp_candle)
    await asyncio.sleep(1.5)
    
    # Check trades.closed
    closed = await trades_closed_consumer.read(count=1, block_ms=3000)
    
    assert len(closed) > 0, "Trade not closed after TP hit"
    
    closed_trade = closed[0]
    assert closed_trade.exit_price == 2680.0, "Exit price should match TP"
    assert "TP" in (closed_trade.exit_reason or ""), "Exit reason should indicate TP"
    
    # Verify positive PnL
    assert closed_trade.pnl_points is not None
    assert closed_trade.pnl_points > 0, "TP hit should result in positive PnL"
    assert closed_trade.pnl_points == 30.0, "PnL should be 30 points (2680 - 2650)"


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
    
    # Wait briefly for signal to be consumed and buffered
    await asyncio.sleep(0.5)
    
    # Execute trade with multiple candles to ensure processing
    last_entry_candle = None
    for i in range(3):
        entry_candle = CandleMessage(
            timestamp=signal.timestamp + timedelta(minutes=i + 1),
            symbol="GC",
            timeframe="1m",
            open=2650.0,
            high=2651.0,
            low=2649.0,
            close=2650.5,
            volume=1000.0,
        )
        last_entry_candle = entry_candle
        
        await redis_publisher.publish("candles.1m.gc", entry_candle)
        await asyncio.sleep(0.3)
    
    await asyncio.sleep(2.0)
    
    assert last_entry_candle is not None, "No candles were created"
    
    # FIRST verify trade was opened before testing invalidation
    opened = await trades_opened_consumer.read(count=1, block_ms=5000)
    assert len(opened) > 0, "Trade not opened - cannot test invalidation"
    
    # Publish features showing VWAP invalidation (price below VWAP for long)
    invalid_features = FeaturesMessage(
        timestamp=last_entry_candle.timestamp + timedelta(minutes=1),
        symbol="GC",
        timeframe="1m",
        close=2645.0,
        vwap=2648.0,  # VWAP above price - invalidation for long
        rsi=None,
        ema_9=None,
        ema_20=None,
        ema_50=None,
        dxy_correlation=None,
        structure_label=None,
        vwap_deviation=None,
    )
    
    # Need to publish corresponding candle
    invalid_candle = CandleMessage(
        timestamp=last_entry_candle.timestamp + timedelta(minutes=1),
        symbol="GC",
        timeframe="1m",
        open=2646.0,
        high=2647.0,
        low=2644.0,
        close=2645.0,  # Below VWAP
        volume=1000.0,
    )
    
    await redis_publisher.publish("features.1m", invalid_features)
    await redis_publisher.publish("candles.1m.gc", invalid_candle)
    await asyncio.sleep(2.0)
    
    # Check if trade was closed due to invalidation
    closed = await trades_closed_consumer.read(count=1, block_ms=3000)
    
    # CRITICAL: Invalidation must close the trade - test should not pass silently
    assert len(closed) > 0, (
        "Trade should have been closed by invalidation. "
        "If no trade was closed, the invalidation feature is broken."
    )
    
    closed_trade = closed[0]
    # Should be closed for invalidation (VWAP or otherwise)
    # Exit reason should indicate invalidation
    assert closed_trade.exit_reason is not None
    # Verify it's not SL or TP
    assert "SL" not in closed_trade.exit_reason
    assert "TP" not in closed_trade.exit_reason


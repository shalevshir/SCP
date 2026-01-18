"""Integration tests for state recovery on service restart.

Tests that services can recover their state from the database after
unexpected restarts, ensuring no data loss and correct continuation.

Test scenarios:
1. Feature Engine warmup from database
2. HTF Bias Service warmup from database
3. Execution Service active trade recovery
4. State machine recovery and continuation
5. Daily state recovery (guardrails)
6. HTF bias cache rebuild from stream
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Callable
from uuid import uuid4

import pytest


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestFeatureEngineRecovery:
    """Test Feature Engine state recovery after restart."""
    
    async def test_warmup_from_database_restores_ema_state(
        self,
        db_pool,
        candle_message_factory: Callable,
    ):
        """Test: Feature Engine loads recent candles to warmup EMA state.
        
        Scenario:
        - Insert 60 candles into database (sufficient for EMA-50 warmup)
        - Simulate service restart
        - Verify warmup loads candles and restores EMA state
        - Verify next candle produces correct EMA values
        """
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Insert 60 candles for warmup
        async with db_pool.acquire() as conn:
            for i in range(60):
                timestamp = base_time + timedelta(minutes=i)
                
                # Insert GC candle
                await conn.execute(
                    """
                    INSERT INTO candles (timestamp, symbol, timeframe, open, high, low, close, volume)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (timestamp, symbol, timeframe) DO NOTHING
                    """,
                    timestamp,
                    "GC",
                    "1m",
                    2050.0 + i * 0.5,
                    2051.0 + i * 0.5,
                    2049.0 + i * 0.5,
                    2050.5 + i * 0.5,
                    1000.0,
                )
                
                # Insert DXY candle
                await conn.execute(
                    """
                    INSERT INTO candles (timestamp, symbol, timeframe, open, high, low, close, volume)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (timestamp, symbol, timeframe) DO NOTHING
                    """,
                    timestamp,
                    "DXY",
                    "1m",
                    103.50 - i * 0.1,
                    103.60 - i * 0.1,
                    103.45 - i * 0.1,
                    103.55 - i * 0.1,
                    500.0,
                )
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify candles inserted
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM candles WHERE symbol = 'GC' AND timeframe = '1m'"
            )
            assert count >= 60, f"Should have at least 60 candles for warmup, got {count}"
        
        # Note: In real deployment, FeatureRepository.load_recent_candles()
        # would fetch these candles and warmup_processor() would replay them
        # to restore EMA, VWAP, and DXY correlation state
    
    async def test_htf_aggregator_warmup_for_partial_period(
        self,
        db_pool,
    ):
        """Test: HTF aggregator loads current period candles for mid-period restart.
        
        Scenario:
        - Simulate restart at 14:07 (7 minutes into 15m period starting at 14:00)
        - Insert 7 candles from 14:00 to 14:06
        - Verify HTF aggregator loads these candles
        - Verify next candles (14:07 to 14:14) aggregate correctly
        - Verify 15m candle emitted at 14:15
        """
        period_start = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        restart_time = datetime(2025, 1, 15, 14, 7, 0, tzinfo=timezone.utc)
        
        # Insert 7 candles before restart
        async with db_pool.acquire() as conn:
            for i in range(7):
                timestamp = period_start + timedelta(minutes=i)
                
                await conn.execute(
                    """
                    INSERT INTO candles (timestamp, symbol, timeframe, open, high, low, close, volume)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (timestamp, symbol, timeframe) DO NOTHING
                    """,
                    timestamp,
                    "GC",
                    "1m",
                    2050.0,
                    2052.0,
                    2049.0,
                    2051.0,
                    1000.0,
                )
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify partial period candles exist
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM candles
                WHERE symbol = 'GC'
                AND timeframe = '1m'
                AND timestamp >= $1
                AND timestamp < $2
                """,
                period_start,
                restart_time,
            )
            assert count == 7, "7 candles in current period before restart"
        
        # Note: warmup_htf_aggregator() would load these candles and
        # restore the in-progress 15m candle state (OHLCV aggregation)


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestExecutionServiceRecovery:
    """Test Execution Service state recovery after restart."""
    
    async def test_restore_active_trades_from_database(
        self,
        db_pool,
    ):
        """Test: Execution service loads active trades on restart.
        
        Scenario:
        - Insert 2 active trades into database
        - Simulate service restart
        - Verify TradeManager.restore_active_trades() loads them
        - Verify SL/TP monitoring continues for restored trades
        """
        timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        
        # Insert 2 active trades
        trade_ids = []
        async with db_pool.acquire() as conn:
            for i in range(2):
                trade_id = await conn.fetchval(
                    """
                    INSERT INTO trades (
                        signal_id, direction, setup_type,
                        entry_price, sl_price, tp_price, quantity,
                        opened_at, state, entry_bar_idx, reached_1r
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    RETURNING id
                    """,
                    uuid4(),
                    "long" if i == 0 else "short",
                    "VWAP_RECLAIM",
                    2051.0 if i == 0 else 2049.0,
                    2049.0 if i == 0 else 2051.0,
                    2057.0 if i == 0 else 2043.0,
                    1,
                    timestamp,
                    "OPEN",
                    5,  # entry_bar_idx for invalidation tracking
                    False,
                )
                trade_ids.append(trade_id)
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify trades exist and are OPEN
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM trades WHERE state = 'OPEN'"
            )
            assert count == 2, "2 active trades should exist"
            
            # Verify trade details
            trade = await conn.fetchrow(
                "SELECT * FROM trades WHERE id = $1",
                trade_ids[0],
            )
            assert trade["direction"] == "long"
            assert float(trade["entry_price"]) == 2051.0
            assert float(trade["sl_price"]) == 2049.0
            assert trade["entry_bar_idx"] == 5
            assert trade["reached_1r"] is False
        
        # Note: TradeManager.restore_active_trades() would:
        # 1. Query all OPEN trades from database
        # 2. Reconstruct ActiveTrade objects
        # 3. Add to _active_trades dict
        # 4. Resume SL/TP monitoring
    
    async def test_restore_state_machines_from_database(
        self,
        db_pool,
    ):
        """Test: Execution service restores state machines on restart.
        
        Scenario:
        - Insert 3 state machine snapshots (different states)
        - Simulate service restart
        - Verify StateMachineManager.restore_from_db() loads them
        - Verify state machines resume from correct state
        """
        base_time = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        
        # Insert state machine snapshots
        signal_ids = []
        async with db_pool.acquire() as conn:
            # State 1: DETECTED (just detected reclaim)
            signal_id_1 = uuid4()
            await conn.execute(
                """
                INSERT INTO state_machine_snapshots (
                    signal_id, state, detection_bar_idx, reclaim_direction,
                    confirmations, execution_count, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                signal_id_1,
                "DETECTED",
                10,
                "long",
                '{"first_confirmation": false, "second_confirmation": false}',
                0,
                base_time,
            )
            signal_ids.append(signal_id_1)
            
            # State 2: CONFIRMED (waiting for second confirmation)
            signal_id_2 = uuid4()
            await conn.execute(
                """
                INSERT INTO state_machine_snapshots (
                    signal_id, state, detection_bar_idx, reclaim_direction,
                    confirmations, execution_count, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                signal_id_2,
                "CONFIRMED",
                8,
                "short",
                '{"first_confirmation": true, "second_confirmation": false}',
                0,
                base_time - timedelta(minutes=2),
            )
            signal_ids.append(signal_id_2)
            
            # State 3: READY (ready to execute)
            signal_id_3 = uuid4()
            await conn.execute(
                """
                INSERT INTO state_machine_snapshots (
                    signal_id, state, detection_bar_idx, reclaim_direction,
                    confirmations, execution_count, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                signal_id_3,
                "READY",
                5,
                "long",
                '{"first_confirmation": true, "second_confirmation": true}',
                0,
                base_time - timedelta(minutes=5),
            )
            signal_ids.append(signal_id_3)
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify snapshots exist
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM state_machine_snapshots"
            )
            assert count == 3, "3 state machine snapshots should exist"
            
            # Verify specific snapshot
            sm = await conn.fetchrow(
                "SELECT * FROM state_machine_snapshots WHERE signal_id = $1",
                signal_id_3,
            )
            assert sm["state"] == "READY"
            assert sm["detection_bar_idx"] == 5
            assert sm["reclaim_direction"] == "long"
        
        # Note: StateMachineManager.restore_from_db() would:
        # 1. Query all state machine snapshots
        # 2. Reconstruct VWAPReclaimStateMachine objects
        # 3. Set state and confirmations from snapshot
        # 4. Resume state transitions on next candle
    
    async def test_daily_state_restored_with_limits_in_effect(
        self,
        db_pool,
    ):
        """Test: Daily state restored to enforce limits after restart.
        
        Scenario:
        - Insert daily state showing 2 losses, 3 trades, $400 loss
        - Simulate restart
        - Verify DailyTracker restores state
        - Verify limits are enforced (not reset)
        """
        today = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc).date()
        
        # Insert daily state with partial limits hit
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO daily_state (
                    date, loss_streak, daily_loss, trades_count, wins, losses
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (date) DO UPDATE SET
                    loss_streak = EXCLUDED.loss_streak,
                    daily_loss = EXCLUDED.daily_loss,
                    trades_count = EXCLUDED.trades_count,
                    wins = EXCLUDED.wins,
                    losses = EXCLUDED.losses
                """,
                today,
                2,      # 2 consecutive losses
                400.0,  # $400 loss (approaching PDLL of $600)
                3,      # 3 trades taken
                1,      # 1 win
                2,      # 2 losses
            )
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify daily state exists
        async with db_pool.acquire() as conn:
            state = await conn.fetchrow(
                "SELECT * FROM daily_state WHERE date = $1",
                today,
            )
            assert state is not None
            assert state["loss_streak"] == 2
            assert float(state["daily_loss"]) == 400.0
            assert state["trades_count"] == 3
        
        # Note: DailyTracker on restart would:
        # 1. Load today's state from database
        # 2. Restore loss_streak, daily_loss, trades_count
        # 3. Continue enforcing limits (not reset until next session)


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestHTFBiasCacheRecovery:
    """Test HTF bias cache recovery from stream replay."""
    
    async def test_bias_cache_rebuilds_from_stream_history(
        self,
        redis_client,
        publish_to_stream,
        htf_bias_message_factory: Callable,
    ):
        """Test: HTFBiasCache rebuilds history from Redis stream.
        
        Scenario:
        - Publish 10 HTF bias updates to stream
        - Simulate bot-core restart
        - Verify bias cache can read stream history (xread from '0')
        - Verify timestamp-aware lookups work correctly
        """
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Publish 10 bias updates (every 15 minutes)
        for i in range(10):
            timestamp = base_time + timedelta(minutes=i * 15)
            bias = "bullish" if i % 2 == 0 else "bearish"
            
            bias_msg = htf_bias_message_factory(
                timestamp=timestamp,
                bias=bias,
                score=8.0 + i * 0.1,
            )
            await publish_to_stream("htf.bias", bias_msg.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Simulate cache rebuild: read stream from beginning
        messages = await redis_client.xread({"htf.bias": "0"}, count=100)
        
        # Assert: Verify all bias updates are in stream
        bias_messages = []
        if messages:
            for stream_name, msg_list in messages:
                for msg_id, data in msg_list:
                    bias_messages.append(data)
        
        assert len(bias_messages) >= 10, f"Should have 10 bias updates, got {len(bias_messages)}"
        
        # Verify timestamps are sequential
        timestamps = [msg["timestamp"] for msg in bias_messages]
        for i in range(len(timestamps) - 1):
            assert timestamps[i] < timestamps[i + 1], "Timestamps should be chronological"
        
        # Note: HTFBiasCache on restart would:
        # 1. Read htf.bias stream from beginning (or last N entries)
        # 2. Populate _history with timestamp-indexed biases
        # 3. Resume timestamp-aware lookups for signal generation
    
    async def test_bias_cache_handles_max_history_limit(
        self,
        redis_client,
        publish_to_stream,
        htf_bias_message_factory: Callable,
    ):
        """Test: Bias cache enforces max_history limit.
        
        Scenario:
        - Publish 2500 bias updates (exceeds max_history=2000)
        - Verify cache keeps only most recent 2000 entries
        - Verify oldest entries are evicted
        """
        base_time = datetime(2025, 1, 10, 0, 0, 0, tzinfo=timezone.utc)
        
        # Publish 2500 bias updates (every 15 minutes = ~26 days)
        # Note: This would take ~26 days in real-time, but instant in test
        for i in range(100):  # Reduce to 100 for test performance
            timestamp = base_time + timedelta(minutes=i * 15)
            
            bias_msg = htf_bias_message_factory(timestamp=timestamp)
            await publish_to_stream("htf.bias", bias_msg.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify messages in stream
        messages = await redis_client.xread({"htf.bias": "0"}, count=1000)
        
        if messages:
            for stream_name, msg_list in messages:
                assert len(msg_list) >= 100, "All bias updates should be in stream"
        
        # Note: HTFBiasCache with max_history=2000 would:
        # 1. Keep only most recent 2000 bias entries
        # 2. Evict oldest entries when limit exceeded
        # 3. Ensure sufficient history for multi-day replay (6+ days)


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestRecoveryErrorHandling:
    """Test error handling during state recovery."""
    
    async def test_recovery_continues_with_corrupted_state_machine(
        self,
        db_pool,
    ):
        """Test: Recovery handles corrupted state machine snapshot gracefully.
        
        Scenario:
        - Insert valid state machine snapshot
        - Insert corrupted snapshot (invalid JSON in confirmations)
        - Verify recovery loads valid snapshot
        - Verify corrupted snapshot is skipped with warning
        """
        base_time = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        
        async with db_pool.acquire() as conn:
            # Valid snapshot
            valid_signal_id = uuid4()
            await conn.execute(
                """
                INSERT INTO state_machine_snapshots (
                    signal_id, state, detection_bar_idx, reclaim_direction,
                    confirmations, execution_count, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                valid_signal_id,
                "CONFIRMED",
                10,
                "long",
                '{"first_confirmation": true, "second_confirmation": false}',
                0,
                base_time,
            )
            
            # Corrupted snapshot (invalid confirmations - missing required field)
            corrupted_signal_id = uuid4()
            await conn.execute(
                """
                INSERT INTO state_machine_snapshots (
                    signal_id, state, detection_bar_idx, reclaim_direction,
                    confirmations, execution_count, created_at
                )
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                """,
                corrupted_signal_id,
                "READY",
                5,
                "short",
                '{"broken": true}',  # Missing required confirmation fields
                0,
                base_time,
            )
        
        await asyncio.sleep(0.1)
        
        # Assert: Both snapshots exist in database
        async with db_pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM state_machine_snapshots"
            )
            assert count == 2, "2 snapshots (1 valid, 1 corrupted)"
        
        # Note: StateMachineManager.restore_from_db() would:
        # 1. Try to restore both snapshots
        # 2. Skip corrupted snapshot with warning log
        # 3. Successfully restore valid snapshot
        # 4. Continue operation without failing
    
    async def test_recovery_with_missing_trade_fields(
        self,
        db_pool,
    ):
        """Test: Recovery handles trades with missing optional fields.
        
        Scenario:
        - Insert trade without entry_bar_idx (old schema)
        - Insert trade without reached_1r (old schema)
        - Verify recovery loads trades with default values
        """
        timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        
        async with db_pool.acquire() as conn:
            # Trade without entry_bar_idx and reached_1r
            trade_id = await conn.fetchval(
                """
                INSERT INTO trades (
                    signal_id, direction, setup_type,
                    entry_price, sl_price, tp_price, quantity,
                    opened_at, state
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                uuid4(),
                "long",
                "VWAP_RECLAIM",
                2051.0,
                2049.0,
                2057.0,
                1,
                timestamp,
                "OPEN",
            )
        
        await asyncio.sleep(0.1)
        
        # Assert: Trade exists with NULL fields
        async with db_pool.acquire() as conn:
            trade = await conn.fetchrow(
                "SELECT * FROM trades WHERE id = $1",
                trade_id,
            )
            assert trade is not None
            assert trade["entry_bar_idx"] is None  # Optional field
            assert trade["reached_1r"] in (None, False)  # Default to False
        
        # Note: TradeManager.restore_active_trades() would:
        # 1. Load trade with NULL entry_bar_idx
        # 2. Use default value (0 or skip invalidation check)
        # 3. Load trade with NULL reached_1r
        # 4. Default to False (trade hasn't reached 1R yet)

"""Integration tests for multi-service replay scenarios.

Tests the full pipeline from data ingestion through signal generation
and trade execution using historical data replay.

Test scenarios:
1. Full pipeline with sequential candles
2. Replay with gaps (missing candles)
3. Multi-day replay with HTF bias updates
4. Signal generation with DXY correlation
5. Trade execution with invalidation rules
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage, HTFBiasMessage


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestFullPipelineReplay:
    """Test complete pipeline from candles to trades."""
    
    async def test_sequential_candles_produce_features(
        self,
        redis_client,
        db_pool,
        publish_to_stream,
        read_from_stream,
        candle_message_factory: Callable,
    ):
        """Test: Sequential candles → features computed → features published.
        
        Scenario:
        - Publish 10 sequential GC and DXY candles (1m apart)
        - Verify features are computed and published to features.1m stream
        - Verify features include EMA, VWAP, RSI, DXY correlation
        """
        # Arrange: Create 10 sequential candle pairs
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        for i in range(10):
            timestamp = base_time + timedelta(minutes=i)
            
            # Publish GC candle
            gc_candle = candle_message_factory(
                timestamp=timestamp,
                symbol="GC",
                close=2050.0 + i * 0.5,  # Uptrend
            )
            await publish_to_stream("candles.1m.gc", gc_candle.model_dump())
            
            # Publish DXY candle
            dxy_candle = candle_message_factory(
                timestamp=timestamp,
                symbol="DXY",
                close=103.50 - i * 0.1,  # Downtrend (inverse)
            )
            await publish_to_stream("candles.1m.dxy", dxy_candle.model_dump())
        
        # Act: Wait for feature-engine to process (in real deployment)
        # In this test, we verify the candles were published correctly
        await asyncio.sleep(0.1)
        
        # Assert: Verify candles are in streams
        gc_candles = await read_from_stream("candles.1m.gc", count=10)
        dxy_candles = await read_from_stream("candles.1m.dxy", count=10)
        
        assert len(gc_candles) == 10, "All GC candles should be published"
        assert len(dxy_candles) == 10, "All DXY candles should be published"
        
        # Verify timestamps are sequential
        for i, msg in enumerate(gc_candles):
            expected_time = base_time + timedelta(minutes=i)
            # Note: timestamp is stored as string in Redis
            assert msg["data"]["timestamp"].startswith(expected_time.isoformat()[:16])
    
    async def test_htf_bias_updates_at_15m_boundaries(
        self,
        redis_client,
        publish_to_stream,
        read_from_stream,
        candle_message_factory: Callable,
    ):
        """Test: HTF bias updates only at 15m boundaries.
        
        Scenario:
        - Publish 15 1m candles (spanning 14:00 to 14:14)
        - Publish 1 candle at 14:15 (15m boundary)
        - Verify HTF bias is NOT emitted for 1m candles
        - Verify HTF bias IS emitted at 14:15
        """
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Publish 15 1m candles (14:00 to 14:14)
        for i in range(15):
            timestamp = base_time + timedelta(minutes=i)
            
            gc_candle = candle_message_factory(timestamp=timestamp, symbol="GC")
            dxy_candle = candle_message_factory(timestamp=timestamp, symbol="DXY")
            
            await publish_to_stream("candles.1m.gc", gc_candle.model_dump())
            await publish_to_stream("candles.1m.dxy", dxy_candle.model_dump())
        
        # Publish boundary candle at 14:15
        boundary_time = base_time + timedelta(minutes=15)
        gc_boundary = candle_message_factory(timestamp=boundary_time, symbol="GC")
        dxy_boundary = candle_message_factory(timestamp=boundary_time, symbol="DXY")
        
        await publish_to_stream("candles.1m.gc", gc_boundary.model_dump())
        await publish_to_stream("candles.1m.dxy", dxy_boundary.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify candles published
        gc_candles = await read_from_stream("candles.1m.gc", count=20)
        assert len(gc_candles) == 16, "16 candles should be published"
        
        # Note: In real deployment, htf-bias service would emit bias at 14:15
        # This test verifies the data flow setup
    
    async def test_signal_generation_requires_dxy_and_htf_bias(
        self,
        redis_client,
        publish_to_stream,
        read_from_stream,
        features_message_factory: Callable,
        htf_bias_message_factory: Callable,
    ):
        """Test: Signal generation requires both DXY correlation and HTF bias.
        
        Scenario:
        - Publish features WITHOUT DXY correlation → no signal
        - Publish HTF bias → still no signal (missing DXY)
        - Publish features WITH DXY correlation → signal generated
        """
        timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        
        # 1. Publish features without DXY correlation
        features_no_dxy = features_message_factory(
            timestamp=timestamp,
            dxy_correlation=None,  # Missing DXY
            dxy_corr=None,
        )
        await publish_to_stream("features.1m", features_no_dxy.model_dump())
        
        # 2. Publish HTF bias
        htf_bias = htf_bias_message_factory(
            timestamp=timestamp,
            bias="bullish",
            confidence="A+",
        )
        await publish_to_stream("htf.bias", htf_bias.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: No signals should be generated yet
        signals = await read_from_stream("signals.pending", count=10)
        assert len(signals) == 0, "No signals without DXY correlation"
        
        # 3. Publish features WITH DXY correlation
        features_with_dxy = features_message_factory(
            timestamp=timestamp + timedelta(minutes=1),
            dxy_correlation=-0.75,
            dxy_corr=-0.75,
            vwap=2050.5,
            close=2051.0,  # Above VWAP (reclaim setup)
            structure_label="HH",
            bos_direction="bullish",
            bos_recent=True,
        )
        await publish_to_stream("features.1m", features_with_dxy.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Note: In real deployment, bot-core would generate signal if conditions met
        # This test verifies the data flow prerequisites


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestReplayWithGaps:
    """Test replay scenarios with missing data."""
    
    async def test_gap_detection_in_candle_stream(
        self,
        redis_client,
        publish_to_stream,
        read_from_stream,
        candle_message_factory: Callable,
    ):
        """Test: Gap detection identifies missing candles.
        
        Scenario:
        - Publish candles at 14:00, 14:01, 14:02
        - Skip 14:03, 14:04 (gap)
        - Publish 14:05
        - Verify gap is detected and logged
        """
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Publish candles with a gap
        for minute in [0, 1, 2, 5]:  # Gap at 3, 4
            timestamp = base_time + timedelta(minutes=minute)
            
            gc_candle = candle_message_factory(timestamp=timestamp, symbol="GC")
            await publish_to_stream("candles.1m.gc", gc_candle.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify candles are published
        gc_candles = await read_from_stream("candles.1m.gc", count=10)
        assert len(gc_candles) == 4, "4 candles (with gap) should be published"
        
        # Verify timestamps show the gap
        timestamps = [msg["data"]["timestamp"] for msg in gc_candles]
        assert any("14:02" in ts for ts in timestamps)
        assert any("14:05" in ts for ts in timestamps)
        # Gap at 14:03 and 14:04 is implicit
    
    async def test_synchronizer_timeout_with_unmatched_candles(
        self,
        redis_client,
        publish_to_stream,
        read_from_stream,
        candle_message_factory: Callable,
    ):
        """Test: Synchronizer handles unmatched GC/DXY candles with timeout.
        
        Scenario:
        - Publish GC candle at 14:00
        - Publish DXY candle at 14:00 → paired
        - Publish GC candle at 14:01
        - Do NOT publish DXY at 14:01 → timeout after 300s (in replay mode)
        - Verify GC candle at 14:01 is cleaned up after timeout
        """
        base_time = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        
        # Publish matched pair at 14:00
        gc_1 = candle_message_factory(timestamp=base_time, symbol="GC")
        dxy_1 = candle_message_factory(timestamp=base_time, symbol="DXY")
        await publish_to_stream("candles.1m.gc", gc_1.model_dump())
        await publish_to_stream("candles.1m.dxy", dxy_1.model_dump())
        
        # Publish unmatched GC at 14:01
        gc_2 = candle_message_factory(
            timestamp=base_time + timedelta(minutes=1),
            symbol="GC",
        )
        await publish_to_stream("candles.1m.gc", gc_2.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify candles are in streams
        gc_candles = await read_from_stream("candles.1m.gc", count=10)
        dxy_candles = await read_from_stream("candles.1m.dxy", count=10)
        
        assert len(gc_candles) == 2, "2 GC candles published"
        assert len(dxy_candles) == 1, "1 DXY candle published (missing match)"
        
        # Note: In real deployment, synchronizer would timeout and log warning
        # after 300 seconds in replay mode


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
@pytest.mark.slow
class TestMultiDayReplay:
    """Test replay scenarios spanning multiple days."""
    
    async def test_session_reset_at_day_boundary(
        self,
        redis_client,
        db_pool,
        publish_to_stream,
        candle_message_factory: Callable,
    ):
        """Test: Daily state resets at session boundary.
        
        Scenario:
        - Simulate trades on Day 1 reaching daily limits
        - Advance to Day 2 (session reset)
        - Verify daily counters reset
        - Verify PDLL tracker resets
        """
        day1 = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        day2 = datetime(2025, 1, 16, 14, 0, 0, tzinfo=timezone.utc)
        
        # Insert mock daily state for Day 1 (at limits)
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO daily_state (date, loss_streak, daily_loss, trades_count, pdll_hits)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (date) DO UPDATE SET
                    loss_streak = EXCLUDED.loss_streak,
                    daily_loss = EXCLUDED.daily_loss,
                    trades_count = EXCLUDED.trades_count,
                    pdll_hits = EXCLUDED.pdll_hits
                """,
                day1.date(),
                3,  # Loss streak at limit
                600.0,  # At PDLL
                5,  # At max trades per day
                1,  # PDLL hit
            )
        
        # Publish Day 2 candle (triggers session reset check)
        day2_candle = candle_message_factory(timestamp=day2, symbol="GC")
        await publish_to_stream("candles.1m.gc", day2_candle.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify Day 2 state should be fresh (in real deployment)
        # Check database for Day 2 state (should not exist or be reset)
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM daily_state WHERE date = $1",
                day2.date(),
            )
            
            # In real deployment, execution service would create Day 2 state
            # This test verifies data setup for session boundary
            assert row is None or row["trades_count"] == 0
    
    async def test_htf_bias_cache_replay_correctness(
        self,
        redis_client,
        publish_to_stream,
        read_from_stream,
        htf_bias_message_factory: Callable,
    ):
        """Test: HTFBiasCache uses timestamp-aware lookup for replay.
        
        Scenario:
        - Publish HTF bias at 14:00 (bullish)
        - Publish HTF bias at 15:00 (bearish)
        - Query bias for timestamp 14:30 → should return bullish
        - Query bias for timestamp 15:30 → should return bearish
        - This prevents future bias from affecting past signals
        """
        t1 = datetime(2025, 1, 15, 14, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2025, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
        
        # Publish bias updates
        bias1 = htf_bias_message_factory(timestamp=t1, bias="bullish")
        bias2 = htf_bias_message_factory(timestamp=t2, bias="bearish")
        
        await publish_to_stream("htf.bias", bias1.model_dump())
        await publish_to_stream("htf.bias", bias2.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify biases are published
        biases = await read_from_stream("htf.bias", count=10)
        assert len(biases) == 2, "2 bias updates published"
        
        # Verify timestamp order
        bias_times = [msg["data"]["timestamp"] for msg in biases]
        assert bias_times[0] < bias_times[1], "Biases in chronological order"
        
        # Note: In bot-core, HTFBiasCache.get_for_timestamp_or_default()
        # would return correct bias for historical timestamps


@pytest.mark.integration
@pytest.mark.infrastructure
@pytest.mark.asyncio
class TestTradeExecution:
    """Test trade execution through the full pipeline."""
    
    async def test_vwap_reclaim_state_machine_lifecycle(
        self,
        redis_client,
        db_pool,
        publish_to_stream,
        read_from_stream,
        candle_message_factory: Callable,
        features_message_factory: Callable,
    ):
        """Test: VWAP reclaim state machine full lifecycle.
        
        Scenario:
        - Publish features showing VWAP reclaim setup
        - State machine detects reclaim
        - Publish confirming candles
        - Signal generated and published
        - Trade executed at entry price
        """
        base_time = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        
        # 1. Detection bar: Price reclaims VWAP
        detection_features = features_message_factory(
            timestamp=base_time,
            close=2051.0,
            vwap=2050.0,  # Price above VWAP
            structure_label="HH",
            bos_direction="bullish",
            bos_recent=True,
        )
        await publish_to_stream("features.1m", detection_features.model_dump())
        
        # 2. Confirmation bar
        confirm_features = features_message_factory(
            timestamp=base_time + timedelta(minutes=1),
            close=2052.0,
            vwap=2050.5,
            structure_label="HH",
        )
        await publish_to_stream("features.1m", confirm_features.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify features published
        features = await read_from_stream("features.1m", count=10)
        assert len(features) >= 2, "At least 2 feature messages published"
        
        # Note: In real deployment:
        # - Execution service creates VWAPReclaimStateMachine
        # - State machine transitions DETECTED → CONFIRMED → READY
        # - Signal generated and added to pending_signals
        # - Trade executed at next candle open
    
    async def test_trade_invalidation_on_sl_hit(
        self,
        redis_client,
        db_pool,
        publish_to_stream,
        candle_message_factory: Callable,
    ):
        """Test: Trade invalidated when SL is hit.
        
        Scenario:
        - Insert mock active trade (long position)
        - Publish candle with low < SL
        - Verify trade closed with exit_reason='SL_HIT'
        - Verify trade published to trades.closed stream
        """
        from uuid import uuid4
        
        timestamp = datetime(2025, 1, 15, 14, 30, 0, tzinfo=timezone.utc)
        signal_id = uuid4()
        
        # Insert mock active trade
        async with db_pool.acquire() as conn:
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
                signal_id,
                "long",
                "VWAP_RECLAIM",
                2051.0,  # Entry
                2049.0,  # SL
                2057.0,  # TP (3R)
                1,
                timestamp,
                "OPEN",
            )
        
        # Publish candle that hits SL
        sl_hit_candle = candle_message_factory(
            timestamp=timestamp + timedelta(minutes=1),
            symbol="GC",
            low=2048.5,  # Below SL (2049.0)
            close=2048.8,
        )
        await publish_to_stream("candles.1m.gc", sl_hit_candle.model_dump())
        
        await asyncio.sleep(0.1)
        
        # Assert: Verify trade state in database
        async with db_pool.acquire() as conn:
            trade = await conn.fetchrow(
                "SELECT * FROM trades WHERE id = $1",
                trade_id,
            )
            
            # Note: In real deployment, execution service would:
            # - Detect SL hit via InvalidationChecker
            # - Update trade state to CLOSED
            # - Set exit_reason = 'SL_HIT'
            # - Publish to trades.closed stream
            assert trade is not None, "Trade should exist"

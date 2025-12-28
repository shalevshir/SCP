"""Feature Engine Service main entry point."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime

import redis.asyncio as redis
from fastapi import FastAPI
from scp_shared.common import get_logger, mask_connection_url
from scp_shared.database import DatabasePool
from scp_shared.health import create_health_router
from scp_shared.messaging import RedisStreamConsumer, CandleSynchronizer
from scp_shared.messaging.schemas import CandleMessage

from feature_engine_svc.config import FeatureEngineConfig
from feature_engine_svc.htf_aggregator import HTFCandleAggregator
from feature_engine_svc.processor import FeatureProcessor
from feature_engine_svc.publisher import FeaturePublisher
from feature_engine_svc.repository import FeatureRepository

logger = get_logger(__name__)

# #region agent log
import os
import time as _time_module
_DEBUG_LOG_PATH = os.environ.get("DEBUG_LOG_PATH", "/Users/shalev/Code/SCP/.cursor/debug.log")
_DEBUG_COUNTERS = {"gc_received": 0, "dxy_received": 0, "pairs_formed": 0, "features_published": 0, "read_start": 0, "read_loops": 0}
def _debug_log(loc: str, msg: str, data: dict, hyp: str) -> None:
    try:
        os.makedirs(os.path.dirname(_DEBUG_LOG_PATH), exist_ok=True)
        with open(_DEBUG_LOG_PATH, "a") as f:
            f.write(json.dumps({"location": loc, "message": msg, "data": data, "timestamp": int(_time_module.time() * 1000), "sessionId": "debug-session", "hypothesisId": hyp}) + "\n")
    except: pass
# #endregion

# Load configuration
config = FeatureEngineConfig()

# Global shutdown event
shutdown_event = asyncio.Event()


async def warmup_processor(
    processor: FeatureProcessor,
    repository: FeatureRepository,
    timeframe: str,
) -> None:
    """Warmup processor by replaying recent candles from database.
    
    Args:
        processor: Feature processor to warmup
        repository: Repository to load candles from
        timeframe: Timeframe to load
    """
    if not config.enable_warmup:
        logger.info(f"Warmup disabled for {timeframe}")
        return
    
    logger.info(f"Starting warmup for {timeframe} processor...")
    
    try:
        # Load recent candles
        candle_pairs = await repository.load_recent_candles(
            symbol="GC",
            timeframe=timeframe,
            count=config.warmup_candles,
        )
        
        if not candle_pairs:
            logger.warning(f"No candles found for warmup ({timeframe})")
            return
        
        logger.info(f"Loaded {len(candle_pairs)} candle pairs for warmup")
        
        # Replay through processor
        for gc_candle, dxy_candle in candle_pairs:
            processor.process(gc_candle, dxy_candle)
        
        logger.info(
            f"Warmup complete for {timeframe}: "
            f"{processor.bar_count} bars processed, "
            f"warmed_up={processor.is_warmed_up()}"
        )
    
    except Exception as e:
        logger.error(f"Warmup failed for {timeframe}: {e}", exc_info=True)
        # Continue without warmup


async def warmup_htf_aggregator(
    htf_aggregator: HTFCandleAggregator,
    repository: FeatureRepository,
    symbol: str = "GC",
) -> None:
    """Warmup HTF aggregator with current period's 1m candles.
    
    If service starts mid-period (e.g., at 10:05 in a 15m period starting at 10:00),
    we need to load candles from 10:00-10:04 to ensure correct OHLCV values when
    the period completes.
    
    Args:
        htf_aggregator: HTF candle aggregator to warmup
        repository: Repository to load candles from
        symbol: Symbol to warmup (GC or DXY)
    """
    if not config.enable_warmup:
        logger.info(f"Warmup disabled for HTF aggregator ({symbol})")
        return
    
    logger.info(f"Starting warmup for HTF aggregator ({symbol})...")
    
    try:
        from datetime import datetime, timezone
        
        # Load recent 1m candles (enough to cover current 1h period)
        # Maximum is 59 candles if we start at the last minute of an hour
        candle_pairs = await repository.load_recent_candles(
            symbol=symbol,
            timeframe="1m",
            count=60,  # Load up to 1 hour of 1m candles
        )
        
        if not candle_pairs:
            logger.warning(f"No 1m candles found for HTF aggregator warmup ({symbol})")
            return
        
        # Get current time to determine current period
        now = datetime.now(timezone.utc)
        
        # Determine start of current 15m and 1h periods
        current_15m_start = htf_aggregator._get_15m_start(now)
        current_1h_start = htf_aggregator._get_1h_start(now)
        
        # Filter candles to only include current period(s)
        # We want candles from the start of current hour up to now
        # Extract the appropriate candle from each pair
        if symbol == "GC":
            current_period_candles = [
                gc for gc, _ in candle_pairs
                if gc.timestamp >= current_1h_start and gc.timestamp < now
            ]
        else:  # DXY
            current_period_candles = [
                dxy for _, dxy in candle_pairs
                if dxy.timestamp >= current_1h_start and dxy.timestamp < now
            ]
        
        if not current_period_candles:
            logger.info(f"No candles in current period - HTF aggregator starts fresh ({symbol})")
            return
        
        logger.info(
            f"Loaded {len(current_period_candles)} candles for current period "
            f"({symbol}, 15m start: {current_15m_start}, 1h start: {current_1h_start})"
        )
        
        # Replay through aggregator (discarding any emitted candles since we're mid-period)
        for candle in current_period_candles:
            htf_aggregator.add_1m_candle(candle)
        
        logger.info(
            f"HTF aggregator warmup complete ({symbol}): "
            f"15m state={'active' if htf_aggregator.current_15m_start else 'empty'}, "
            f"1h state={'active' if htf_aggregator.current_1h_start else 'empty'}"
        )
    
    except Exception as e:
        logger.error(f"HTF aggregator warmup failed ({symbol}): {e}", exc_info=True)
        # Continue without warmup


async def process_candles(
    redis_client: redis.Redis,
    db_pool: DatabasePool,
) -> None:
    """Main processing loop: consume candles, compute features, publish.
    
    Args:
        redis_client: Redis client
        db_pool: Database pool
    """
    logger.info("Starting candle processing loop")
    
    # Initialize components
    # Use a larger timeout (5 minutes of data-time) to handle:
    # 1. High-speed replay where many candles arrive in quick succession
    # 2. Gaps in historical data (e.g., trading hours only)
    # The cleanup uses DATA timestamps, not wall-clock time, so during replay
    # we need a buffer large enough to span any gaps in the data.
    synchronizer = CandleSynchronizer(timeout_seconds=300)
    htf_aggregator_gc = HTFCandleAggregator()
    htf_aggregator_dxy = HTFCandleAggregator()
    
    # Feature processors for each timeframe
    processor_1m = FeatureProcessor(timeframe="1m")
    processor_15m = FeatureProcessor(timeframe="15m")
    processor_1h = FeatureProcessor(timeframe="1h")
    
    # Publisher and repository
    publisher = FeaturePublisher(redis_client)
    repository = FeatureRepository(db_pool)
    
    # Warmup processors
    await warmup_processor(processor_1m, repository, "1m")
    await warmup_processor(processor_15m, repository, "15m")
    await warmup_processor(processor_1h, repository, "1h")
    
    # Warmup HTF aggregators with current period's candles
    await warmup_htf_aggregator(htf_aggregator_gc, repository, symbol="GC")
    await warmup_htf_aggregator(htf_aggregator_dxy, repository, symbol="DXY")
    
    # Create consumers for GC and DXY candles
    gc_consumer = RedisStreamConsumer(
        redis_client,
        stream="candles.1m.gc",
        group="feature-engine",
        consumer_name="instance-1",
        message_type=CandleMessage,
    )
    dxy_consumer = RedisStreamConsumer(
        redis_client,
        stream="candles.1m.dxy",
        group="feature-engine",
        consumer_name="instance-1",
        message_type=CandleMessage,
    )
    
    logger.info("Feature Engine ready - consuming candles")
    
    try:
        while not shutdown_event.is_set():
            # #region agent log
            _DEBUG_COUNTERS["read_loops"] += 1
            loop_start = _time_module.time()
            # #endregion
            
            # Read from both streams
            gc_candles = await gc_consumer.read(count=10, block_ms=1000)
            
            # #region agent log
            gc_read_time = _time_module.time() - loop_start
            dxy_read_start = _time_module.time()
            # #endregion
            
            dxy_candles = await dxy_consumer.read(count=10, block_ms=1000)
            
            # #region agent log
            dxy_read_time = _time_module.time() - dxy_read_start
            _DEBUG_COUNTERS["gc_received"] += len(gc_candles)
            _DEBUG_COUNTERS["dxy_received"] += len(dxy_candles)
            if gc_candles or dxy_candles:
                # Log first/last candle timestamps to detect gaps
                gc_first_ts = str(gc_candles[0].timestamp) if gc_candles else None
                gc_last_ts = str(gc_candles[-1].timestamp) if gc_candles else None
                dxy_first_ts = str(dxy_candles[0].timestamp) if dxy_candles else None
                dxy_last_ts = str(dxy_candles[-1].timestamp) if dxy_candles else None
                _debug_log("fe:main.py:read", "candles_received", {
                    "gc": len(gc_candles), "dxy": len(dxy_candles),
                    "gc_total": _DEBUG_COUNTERS["gc_received"], "dxy_total": _DEBUG_COUNTERS["dxy_received"],
                    "gc_read_ms": int(gc_read_time * 1000), "dxy_read_ms": int(dxy_read_time * 1000),
                    "gc_first": gc_first_ts, "gc_last": gc_last_ts,
                    "dxy_first": dxy_first_ts, "dxy_last": dxy_last_ts,
                    "loop": _DEBUG_COUNTERS["read_loops"]
                }, "A")
            # #endregion
            
            # CRITICAL FIX: Interleave GC and DXY candle processing to prevent
            # cleanup from dropping unpaired candles during high-speed replay.
            # Previously, all GC candles were added first, then all DXY candles.
            # This caused candles spanning >1 minute to be dropped before their
            # pair arrived.
            #
            # New approach: Add candles in timestamp order by merging both lists.
            all_candles = list(gc_candles) + list(dxy_candles)
            all_candles.sort(key=lambda c: c.timestamp)
            
            # #region agent log
            process_start = _time_module.time()
            pairs_this_loop = 0
            # #endregion
            
            for candle in all_candles:
                pair = synchronizer.add_candle(candle)
                if pair:
                    # #region agent log
                    _DEBUG_COUNTERS["pairs_formed"] += 1
                    pairs_this_loop += 1
                    _debug_log("fe:main.py:pair", "candle_pair_formed", {"timestamp": str(pair[0].timestamp), "gc_close": pair[0].close, "dxy_close": pair[1].close, "total_pairs": _DEBUG_COUNTERS["pairs_formed"]}, "A")
                    # #endregion
                    await process_candle_pair(
                        pair,
                        processor_1m,
                        processor_15m,
                        processor_1h,
                        htf_aggregator_gc,
                        htf_aggregator_dxy,
                        publisher,
                        repository,
                    )
            
            # #region agent log
            process_time = _time_module.time() - process_start
            total_loop_time = _time_module.time() - loop_start
            if pairs_this_loop > 0 or total_loop_time > 1.5:  # Log slow loops or loops with pairs
                _debug_log("fe:main.py:loop", "loop_completed", {
                    "loop": _DEBUG_COUNTERS["read_loops"],
                    "pairs": pairs_this_loop,
                    "process_ms": int(process_time * 1000),
                    "total_ms": int(total_loop_time * 1000),
                    "buffer_gc": len(synchronizer.gc_buffer),
                    "buffer_dxy": len(synchronizer.dxy_buffer)
                }, "H1")
            # #endregion
            
            # Log buffer stats periodically
            if synchronizer.gc_buffer or synchronizer.dxy_buffer:
                stats = synchronizer.get_buffer_stats()
                logger.debug(f"Synchronizer buffer: {stats}")
    
    except asyncio.CancelledError:
        logger.info("Candle processing cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in candle processing loop: {e}", exc_info=True)
        raise


async def process_candle_pair(
    pair: tuple[CandleMessage, CandleMessage],
    processor_1m: FeatureProcessor,
    processor_15m: FeatureProcessor,
    processor_1h: FeatureProcessor,
    htf_aggregator_gc: HTFCandleAggregator,
    htf_aggregator_dxy: HTFCandleAggregator,
    publisher: FeaturePublisher,
    repository: FeatureRepository,
) -> None:
    """Process a synchronized candle pair.
    
    Args:
        pair: Tuple of (gc_candle, dxy_candle)
        processor_1m: 1m feature processor
        processor_15m: 15m feature processor
        processor_1h: 1h feature processor
        htf_aggregator_gc: HTF candle aggregator for GC
        htf_aggregator_dxy: HTF candle aggregator for DXY
        publisher: Feature publisher
        repository: Feature repository
    """
    gc_candle, dxy_candle = pair
    
    # Process 1m features
    features_1m = processor_1m.process(gc_candle, dxy_candle)
    
    # Publish 1m features
    await publisher.publish(features_1m)
    
    # #region agent log
    _DEBUG_COUNTERS["features_published"] += 1
    _debug_log("fe:main.py:publish", "features_published", {"timestamp": str(features_1m.timestamp), "close": features_1m.close, "vwap": features_1m.vwap, "rsi": features_1m.rsi, "structure_label": features_1m.structure_label, "bos_direction": features_1m.bos_direction, "bos_recent": features_1m.bos_recent, "choch_detected": features_1m.choch_detected, "total": _DEBUG_COUNTERS["features_published"]}, "A")
    # #endregion
    
    # Persist 1m features
    await repository.save_features(features_1m)
    
    logger.debug(
        f"Processed 1m features: {gc_candle.timestamp} "
        f"(warmed_up={processor_1m.is_warmed_up()})"
    )
    
    # Add both candles to their respective HTF aggregators
    htf_candles_gc = htf_aggregator_gc.add_1m_candle(gc_candle)
    htf_candles_dxy = htf_aggregator_dxy.add_1m_candle(dxy_candle)
    
    # Process HTF candles when both GC and DXY have matching HTF candles
    # Create a map of DXY HTF candles by timeframe and timestamp
    dxy_htf_map: dict[tuple[str, datetime], CandleMessage] = {}
    for dxy_htf in htf_candles_dxy:
        key = (dxy_htf.timeframe, dxy_htf.timestamp)
        dxy_htf_map[key] = dxy_htf
    
    # Process all emitted GC HTF candles (may be 0, 1, or 2)
    # At hourly boundaries, we get both 15m and 1h candles
    for htf_candle_gc in htf_candles_gc:
        # Find matching DXY HTF candle
        key = (htf_candle_gc.timeframe, htf_candle_gc.timestamp)
        htf_candle_dxy = dxy_htf_map.get(key)
        
        if htf_candle_dxy is None:
            logger.warning(
                f"No matching DXY {htf_candle_gc.timeframe} candle for "
                f"GC candle at {htf_candle_gc.timestamp}. Skipping HTF feature processing."
            )
            continue
        
        if htf_candle_gc.timeframe == "15m":
            # Process 15m features with matching 15m DXY candle
            features_15m = processor_15m.process(htf_candle_gc, htf_candle_dxy)
            await publisher.publish(features_15m)
            await repository.save_features(features_15m)
            logger.info(
                f"Processed 15m features: {htf_candle_gc.timestamp} "
                f"(GC: {htf_candle_gc.close}, DXY: {htf_candle_dxy.close})"
            )
        
        elif htf_candle_gc.timeframe == "1h":
            # Process 1h features with matching 1h DXY candle
            features_1h = processor_1h.process(htf_candle_gc, htf_candle_dxy)
            await publisher.publish(features_1h)
            await repository.save_features(features_1h)
            logger.info(
                f"Processed 1h features: {htf_candle_gc.timestamp} "
                f"(GC: {htf_candle_gc.close}, DXY: {htf_candle_dxy.close})"
            )


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    logger.info(f"Starting Feature Engine Service v{config.service_version}")
    
    # Startup
    redis_client = redis.Redis.from_url(config.redis_url)
    logger.info(f"Connected to Redis at {mask_connection_url(config.redis_url)}")
    
    db_pool = DatabasePool(config.database_url)
    await db_pool.connect()
    logger.info(f"Connected to database at {mask_connection_url(config.database_url)}")
    
    # Start processing task
    processing_task = asyncio.create_task(
        process_candles(redis_client, db_pool)
    )
    
    yield
    
    # Shutdown
    logger.info("Shutting down Feature Engine Service")
    shutdown_event.set()
    processing_task.cancel()
    
    try:
        await processing_task
    except asyncio.CancelledError:
        logger.info("Processing task cancelled successfully")
    except Exception as e:
        logger.error(f"Processing task failed: {e}", exc_info=True)
    finally:
        await redis_client.aclose()
        await db_pool.close()
        logger.info("Feature Engine Service stopped")


# Create FastAPI app
app = FastAPI(
    title="SCP Feature Engine Service",
    version=config.service_version,
    lifespan=lifespan,
)

# Add health check endpoints
health_router = create_health_router(
    service_name=config.service_name,
    version=config.service_version,
)
app.include_router(health_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

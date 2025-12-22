"""Feature Engine Service main entry point."""

import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as redis
from common.logger import get_logger
from fastapi import FastAPI
from scp_shared.database import DatabasePool
from scp_shared.health import create_health_router
from scp_shared.messaging import RedisStreamConsumer
from scp_shared.messaging.schemas import CandleMessage

from feature_engine_svc.config import FeatureEngineConfig
from feature_engine_svc.htf_aggregator import HTFCandleAggregator
from feature_engine_svc.processor import FeatureProcessor
from feature_engine_svc.publisher import FeaturePublisher
from feature_engine_svc.repository import FeatureRepository
from feature_engine_svc.synchronizer import CandleSynchronizer

logger = get_logger(__name__)

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
) -> None:
    """Warmup HTF aggregator with current period's 1m candles.
    
    If service starts mid-period (e.g., at 10:05 in a 15m period starting at 10:00),
    we need to load candles from 10:00-10:04 to ensure correct OHLCV values when
    the period completes.
    
    Args:
        htf_aggregator: HTF candle aggregator to warmup
        repository: Repository to load candles from
    """
    if not config.enable_warmup:
        logger.info("Warmup disabled for HTF aggregator")
        return
    
    logger.info("Starting warmup for HTF aggregator...")
    
    try:
        from datetime import datetime, timezone
        
        # Load recent 1m candles (enough to cover current 1h period)
        # Maximum is 59 candles if we start at the last minute of an hour
        candle_pairs = await repository.load_recent_candles(
            symbol="GC",
            timeframe="1m",
            count=60,  # Load up to 1 hour of 1m candles
        )
        
        if not candle_pairs:
            logger.warning("No 1m candles found for HTF aggregator warmup")
            return
        
        # Get current time to determine current period
        now = datetime.now(timezone.utc)
        
        # Determine start of current 15m and 1h periods
        current_15m_start = htf_aggregator._get_15m_start(now)
        current_1h_start = htf_aggregator._get_1h_start(now)
        
        # Filter candles to only include current period(s)
        # We want candles from the start of current hour up to now
        current_period_candles = [
            (gc, dxy) for gc, dxy in candle_pairs
            if gc.timestamp >= current_1h_start and gc.timestamp < now
        ]
        
        if not current_period_candles:
            logger.info("No candles in current period - HTF aggregator starts fresh")
            return
        
        logger.info(
            f"Loaded {len(current_period_candles)} candles for current period "
            f"(15m start: {current_15m_start}, 1h start: {current_1h_start})"
        )
        
        # Replay through aggregator (discarding any emitted candles since we're mid-period)
        for gc_candle, _ in current_period_candles:
            htf_aggregator.add_1m_candle(gc_candle)
        
        logger.info(
            f"HTF aggregator warmup complete: "
            f"15m state={'active' if htf_aggregator.current_15m_start else 'empty'}, "
            f"1h state={'active' if htf_aggregator.current_1h_start else 'empty'}"
        )
    
    except Exception as e:
        logger.error(f"HTF aggregator warmup failed: {e}", exc_info=True)
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
    synchronizer = CandleSynchronizer(timeout_seconds=60)
    htf_aggregator = HTFCandleAggregator()
    
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
    
    # Warmup HTF aggregator with current period's candles
    await warmup_htf_aggregator(htf_aggregator, repository)
    
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
            # Read from both streams
            gc_candles = await gc_consumer.read(count=10, block_ms=1000)
            dxy_candles = await dxy_consumer.read(count=10, block_ms=1000)
            
            # Add to synchronizer
            for candle in gc_candles:
                pair = synchronizer.add_candle(candle)
                if pair:
                    await process_candle_pair(
                        pair,
                        processor_1m,
                        processor_15m,
                        processor_1h,
                        htf_aggregator,
                        publisher,
                        repository,
                    )
            
            for candle in dxy_candles:
                pair = synchronizer.add_candle(candle)
                if pair:
                    await process_candle_pair(
                        pair,
                        processor_1m,
                        processor_15m,
                        processor_1h,
                        htf_aggregator,
                        publisher,
                        repository,
                    )
            
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
    htf_aggregator: HTFCandleAggregator,
    publisher: FeaturePublisher,
    repository: FeatureRepository,
) -> None:
    """Process a synchronized candle pair.
    
    Args:
        pair: Tuple of (gc_candle, dxy_candle)
        processor_1m: 1m feature processor
        processor_15m: 15m feature processor
        processor_1h: 1h feature processor
        htf_aggregator: HTF candle aggregator
        publisher: Feature publisher
        repository: Feature repository
    """
    gc_candle, dxy_candle = pair
    
    # Process 1m features
    features_1m = processor_1m.process(gc_candle, dxy_candle)
    
    # Publish 1m features
    await publisher.publish(features_1m)
    
    # Persist 1m features
    await repository.save_features(features_1m)
    
    logger.debug(
        f"Processed 1m features: {gc_candle.timestamp} "
        f"(warmed_up={processor_1m.is_warmed_up()})"
    )
    
    # Check for HTF boundaries
    htf_candle = htf_aggregator.add_1m_candle(gc_candle)
    
    if htf_candle:
        # Get corresponding DXY HTF candle (assume same timestamp)
        # In production, would need to aggregate DXY separately
        # For now, use the current DXY candle as proxy
        
        if htf_candle.timeframe == "15m":
            # Process 15m features
            features_15m = processor_15m.process(htf_candle, dxy_candle)
            await publisher.publish(features_15m)
            await repository.save_features(features_15m)
            logger.info(f"Processed 15m features: {htf_candle.timestamp}")
        
        elif htf_candle.timeframe == "1h":
            # Process 1h features
            features_1h = processor_1h.process(htf_candle, dxy_candle)
            await publisher.publish(features_1h)
            await repository.save_features(features_1h)
            logger.info(f"Processed 1h features: {htf_candle.timestamp}")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    logger.info(f"Starting Feature Engine Service v{config.service_version}")
    
    # Startup
    redis_client = redis.Redis.from_url(config.redis_url)
    logger.info(f"Connected to Redis at {config.redis_url}")
    
    db_pool = DatabasePool(config.database_url)
    await db_pool.connect()
    logger.info(f"Connected to database at {config.database_url}")
    
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

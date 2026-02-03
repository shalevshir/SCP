"""HTF Bias Service main entry point."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime

import redis.asyncio as redis
from fastapi import FastAPI
from scp_shared.common import get_logger, mask_connection_url
from scp_shared.database import DatabasePool
from scp_shared.health import create_health_router
from scp_shared.messaging import RedisStreamConsumer, CandleSynchronizer
from scp_shared.messaging.schemas import CandleMessage
from scp_shared.metrics import create_metrics_router

from htf_bias_svc.config import HTFBiasConfig
from htf_bias_svc import metrics as bias_metrics
from htf_bias_svc.processor import HTFBiasProcessor
from htf_bias_svc.publisher import BiasPublisher
from htf_bias_svc.repository import BiasRepository

logger = get_logger(__name__)

# Load configuration
config = HTFBiasConfig()

# Global shutdown event
shutdown_event = asyncio.Event()


async def warmup_from_stream(
    redis_client: redis.Redis,
    processor: HTFBiasProcessor,
    repository: BiasRepository,
) -> bool:
    """Attempt warmup from Redis streams for HTF Bias with database persistence.

    Consumes warmup candles from Redis streams, processes them through the
    HTF bias processor, and persists bias records at HTF boundaries to the
    database for historical analysis.

    Args:
        redis_client: Redis client
        processor: HTF bias processor to warmup
        repository: Repository for database persistence

    Returns:
        True if successful, False if should fall back to database
    """
    from scp_shared.messaging.warmup_consumer import (
        consume_warmup_stream,
        wait_for_warmup_ready,
    )

    # Wait for warmup data to be available (replay script or data-adapter publishes it)
    warmup_ready = await wait_for_warmup_ready(
        redis_client,
        timeout_seconds=config.warmup_stream_timeout_seconds,
    )
    if not warmup_ready:
        logger.info("Warmup streams not available - will use database fallback")
        return False

    # Consume GC and DXY warmup streams
    gc_candles = await consume_warmup_stream(
        redis_client,
        "warmup.candles.1m.gc",
        timeout_seconds=config.warmup_stream_timeout_seconds,
    )
    dxy_candles = await consume_warmup_stream(
        redis_client,
        "warmup.candles.1m.dxy",
        timeout_seconds=config.warmup_stream_timeout_seconds,
    )

    if not gc_candles or not dxy_candles:
        logger.warning("Failed to consume warmup streams - will use database fallback")
        return False

    # Pair candles by timestamp and process (need all candles for structure detection)
    gc_dict = {c.timestamp: c for c in gc_candles}
    dxy_dict = {c.timestamp: c for c in dxy_candles}
    common_ts = sorted(set(gc_dict.keys()) & set(dxy_dict.keys()))

    # Require at least 60 candles (1 hour) for minimum viable warmup
    # Full 1440 (24h) is ideal but markets may be closed
    min_warmup_candles = 60
    if len(common_ts) < min_warmup_candles:
        logger.warning(
            f"Insufficient warmup candles: {len(common_ts)}/{min_warmup_candles} minimum - "
            f"will use database fallback"
        )
        return False

    logger.info(
        f"Processing {len(common_ts)} warmup candle pairs from Redis streams "
        f"(range: {common_ts[0]} to {common_ts[-1]})"
    )

    # Process all candles through HTFBiasProcessor and collect bias at HTF boundaries
    all_bias: list = []
    for ts in common_ts:
        bias = processor.process(gc_dict[ts], dxy_dict[ts])
        # Only collect non-None bias (produced at HTF boundaries like 15m)
        if bias is not None:
            all_bias.append(bias)

    # Batch persist bias records to database
    if all_bias:
        logger.info(f"Persisting {len(all_bias)} warmup bias records to database...")
        await repository.save_bias_batch(all_bias)

    # Log buffer sizes after warmup
    calc = processor.calculator
    logger.info(
        f"Warmup complete from Redis streams: 1H buffer={len(calc.df_1h_buffer)} bars, "
        f"15M buffer={len(calc.df_15m_buffer)} bars, "
        f"DXY 1H buffer={len(calc.dxy_1h_buffer)} bars, "
        f"persisted {len(all_bias)} bias records to database"
    )

    # Log structure detection status
    features_1h = calc.get_current_features_1h()
    features_15m = calc.get_current_features_15m()
    logger.info(
        f"After warmup: structure_1h={features_1h.get('structure_label')}, "
        f"structure_15m={features_15m.get('structure_label')}"
    )

    # Update metrics with final warmup state so dashboard shows correct initial values
    if all_bias:
        mode = config.service_mode
        service = config.service_name
        last_bias = all_bias[-1]
        bias_metrics.update_bias_metrics(last_bias.bias, mode, service)
        bias_metrics.update_htf_detail_metrics(last_bias, mode, service)
        logger.info("Updated HTF bias metrics with warmup end state")

    # Signal to replay script that htf-bias has consumed warmup data
    try:
        await redis_client.hset(
            "warmup:status",
            mapping={"htf_bias_consumed": "true"},
        )
        logger.info("Set htf_bias_consumed marker in warmup:status")
    except Exception as e:
        logger.warning(f"Failed to set warmup consumed marker: {e}")

    return True


async def warmup_processor(
    processor: HTFBiasProcessor,
    repository: BiasRepository,
    before_timestamp: datetime | None = None,
) -> None:
    """Warmup processor by replaying recent candles from database.

    Args:
        processor: HTF bias processor to warmup
        repository: Repository to load candles from
        before_timestamp: Only load candles before this timestamp (for replay alignment)
    """
    if not config.enable_warmup:
        logger.info("Warmup disabled for HTF bias processor")
        return

    logger.info(
        f"Starting warmup for HTF bias processor (before_timestamp={before_timestamp})..."
    )

    try:
        # Load recent candles
        candle_pairs = await repository.load_recent_candles(
            count=config.warmup_candles,
            before_timestamp=before_timestamp,
        )

        if not candle_pairs:
            logger.warning("No candles found for warmup")
            return

        # Log warmup data range
        first_ts = candle_pairs[0][0].timestamp
        last_ts = candle_pairs[-1][0].timestamp
        logger.info(
            f"Loaded {len(candle_pairs)} candle pairs for warmup: {first_ts} to {last_ts}"
        )

        # Replay through processor, keeping track of last bias for metrics
        last_bias = None
        for gc_candle, dxy_candle in candle_pairs:
            # Process returns None until sufficient data accumulated
            bias = processor.process(gc_candle, dxy_candle)
            if bias is not None:
                last_bias = bias

        # Log buffer sizes after warmup
        calc = processor.calculator
        logger.info(
            f"Warmup complete: 1H buffer={len(calc.df_1h_buffer)} bars, "
            f"15M buffer={len(calc.df_15m_buffer)} bars, "
            f"DXY 1H buffer={len(calc.dxy_1h_buffer)} bars"
        )

        # Log structure detection status
        features_1h = calc.get_current_features_1h()
        features_15m = calc.get_current_features_15m()
        logger.info(
            f"After warmup: structure_1h={features_1h.get('structure_label')}, "
            f"structure_15m={features_15m.get('structure_label')}"
        )

        # Update metrics with final warmup state so dashboard shows correct initial values
        if last_bias is not None:
            mode = config.service_mode
            service = config.service_name
            bias_metrics.update_bias_metrics(last_bias.bias, mode, service)
            bias_metrics.update_htf_detail_metrics(last_bias, mode, service)
            logger.info("Updated HTF bias metrics with warmup end state")

    except Exception as e:
        logger.error(f"Warmup failed: {e}", exc_info=True)
        # Continue without warmup


async def warmup_processor_with_fallback(
    redis_client: redis.Redis,
    processor: HTFBiasProcessor,
    repository: BiasRepository,
    before_timestamp: datetime | None = None,
) -> None:
    """Warmup processor from streams (preferred) or database (fallback).

    Args:
        redis_client: Redis client
        processor: HTF bias processor to warmup
        repository: Repository for database fallback
        before_timestamp: Only load candles before this timestamp (for replay alignment)
    """
    if not config.enable_warmup:
        logger.info("Warmup disabled for HTF bias processor")
        return

    # Try stream warmup first (works for both live mode AND replay mode)
    # The replay script now publishes warmup data to Redis streams before replay starts
    if config.warmup_use_redis_streams:
        success = await warmup_from_stream(redis_client, processor, repository)
        if success:
            return

    # Fall back to database warmup (existing logic)
    logger.info("Using database warmup for HTF bias")
    await warmup_processor(processor, repository, before_timestamp)


async def process_candles(
    redis_client: redis.Redis,
    db_pool: DatabasePool,
) -> None:
    """Main processing loop: consume candles, compute bias, publish.

    Args:
        redis_client: Redis client
        db_pool: Database pool
    """
    logger.info("Starting candle processing loop")

    # Initialize components
    # Use 300 seconds (5 minutes of data-time) to handle high-speed replay
    # where many candles arrive in quick succession
    synchronizer = CandleSynchronizer(timeout_seconds=300)
    processor = HTFBiasProcessor()
    publisher = BiasPublisher(redis_client)
    repository = BiasRepository(db_pool)

    # Check for replay start timestamp from environment
    # This is set by the replay script so warmup loads data BEFORE the replay starts
    before_timestamp: datetime | None = None
    replay_start_str = os.environ.get("REPLAY_START_TIMESTAMP")
    if replay_start_str:
        try:
            before_timestamp = datetime.fromisoformat(
                replay_start_str.replace("Z", "+00:00")
            )
            logger.info(
                f"Replay mode detected: warmup will load candles before {before_timestamp}"
            )
        except ValueError:
            logger.warning(f"Invalid REPLAY_START_TIMESTAMP format: {replay_start_str}")

    # Warmup processor (use new wrapper with stream-first, database-fallback)
    await warmup_processor_with_fallback(
        redis_client, processor, repository, before_timestamp
    )

    # Create consumers for GC and DXY candles
    gc_consumer = RedisStreamConsumer(
        redis_client,
        stream="candles.1m.gc",
        group="htf-bias",
        consumer_name="instance-1",
        message_type=CandleMessage,
    )
    dxy_consumer = RedisStreamConsumer(
        redis_client,
        stream="candles.1m.dxy",
        group="htf-bias",
        consumer_name="instance-1",
        message_type=CandleMessage,
    )

    logger.info("HTF Bias Service ready - consuming candles")

    try:
        while not shutdown_event.is_set():
            # Read from both streams
            gc_candles = await gc_consumer.read(count=10, block_ms=1000)
            dxy_candles = await dxy_consumer.read(count=10, block_ms=1000)

            # Sort all candles by timestamp to prevent cleanup from dropping
            # unpaired candles during high-speed replay
            all_candles = list(gc_candles) + list(dxy_candles)
            all_candles.sort(key=lambda c: c.timestamp)

            # Add to synchronizer
            for candle in all_candles:
                pair = synchronizer.add_candle(candle)
                if pair:
                    await process_candle_pair(
                        pair,
                        processor,
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
    processor: HTFBiasProcessor,
    publisher: BiasPublisher,
    repository: BiasRepository,
) -> None:
    """Process a synchronized candle pair.

    Args:
        pair: Tuple of (gc_candle, dxy_candle)
        processor: HTF bias processor
        publisher: Bias publisher
        repository: Bias repository
    """
    gc_candle, dxy_candle = pair

    # Get metric labels
    mode = config.service_mode
    service = config.service_name

    # METRIC: Count 1m bars processed
    bias_metrics.htf_bars_processed_total.labels(
        mode=mode, service=service, timeframe="1m"
    ).inc()

    # Process through HTF bias calculator (with timing)
    with bias_metrics.htf_processing_seconds.labels(mode=mode, service=service).time():
        bias = processor.process(gc_candle, dxy_candle)

    # Only publish and persist if bias was computed (at HTF boundary)
    if bias is not None:
        # Publish to Redis stream
        await publisher.publish(bias)

        # Persist to database
        await repository.save_bias(bias)

        # METRIC: Update bias state and track changes
        bias_metrics.update_bias_metrics(bias.bias, mode, service)

        # METRIC: Update detailed bias metrics for trader dashboard
        bias_metrics.update_htf_detail_metrics(bias, mode, service)

        logger.info(
            f"HTF bias updated: {bias.bias} "
            f"(score: {bias.score:.1f}, confidence: {bias.confidence}, "
            f"timestamp: {gc_candle.timestamp})"
        )
    else:
        logger.debug(f"Processed candles at {gc_candle.timestamp} (no bias update)")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    logger.info(f"Starting HTF Bias Service v{config.service_version}")

    # Startup
    redis_client = redis.Redis.from_url(config.redis_url)
    logger.info(f"Connected to Redis at {mask_connection_url(config.redis_url)}")

    db_pool = DatabasePool(config.database_url)
    await db_pool.connect()
    logger.info(f"Connected to database at {mask_connection_url(config.database_url)}")

    # Initialize HTF bias metrics with defaults
    mode = config.service_mode
    service = config.service_name
    bias_metrics.htf_bias_current.labels(mode=mode, service=service).set(0.0)
    bias_metrics.htf_bias_score.labels(mode=mode, service=service).set(0.0)
    bias_metrics.htf_bias_confidence.labels(mode=mode, service=service).set(0.0)
    bias_metrics.htf_dxy_aligned.labels(mode=mode, service=service).set(0.0)
    bias_metrics.htf_chop_detected.labels(mode=mode, service=service).set(0.0)
    bias_metrics.htf_conflict_detected.labels(mode=mode, service=service).set(0.0)
    bias_metrics.htf_vwap_trend_confirmed.labels(mode=mode, service=service).set(0.0)
    bias_metrics.htf_bos_detected.labels(mode=mode, service=service).set(0.0)
    bias_metrics.htf_liquidity_sweep_detected.labels(mode=mode, service=service).set(
        0.0
    )
    bias_metrics.htf_structure_15m.labels(mode=mode, service=service).set(0.0)
    bias_metrics.htf_structure_1h.labels(mode=mode, service=service).set(0.0)
    bias_metrics.htf_seasonality_adjustment.labels(mode=mode, service=service).set(0.0)
    logger.info("Initialized HTF bias metrics with default values")

    # Start processing task
    processing_task = asyncio.create_task(process_candles(redis_client, db_pool))

    yield

    # Shutdown
    logger.info("Shutting down HTF Bias Service")
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
        logger.info("HTF Bias Service stopped")


# Create FastAPI app
app = FastAPI(
    title="SCP HTF Bias Service",
    version=config.service_version,
    lifespan=lifespan,
)

# Add health check endpoints
health_router = create_health_router(
    service_name=config.service_name,
    version=config.service_version,
)
app.include_router(health_router)

# Add metrics endpoint
metrics_router = create_metrics_router()
app.include_router(metrics_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8003)

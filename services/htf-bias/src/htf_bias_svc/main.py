"""HTF Bias Service main entry point."""

import asyncio
import json
from contextlib import asynccontextmanager

import redis.asyncio as redis
from scp_shared.common import get_logger, mask_connection_url
from fastapi import FastAPI
from scp_shared.database import DatabasePool
from scp_shared.health import create_health_router
from scp_shared.messaging import RedisStreamConsumer, CandleSynchronizer
from scp_shared.messaging.schemas import CandleMessage

from htf_bias_svc.config import HTFBiasConfig
from htf_bias_svc.processor import HTFBiasProcessor
from htf_bias_svc.publisher import BiasPublisher
from htf_bias_svc.repository import BiasRepository

logger = get_logger(__name__)

# #region agent log
import os
import time as _time_module
_DEBUG_LOG_PATH = os.environ.get("DEBUG_LOG_PATH", "/Users/shalev/Code/SCP/.cursor/debug.log")
_DEBUG_COUNTERS = {"gc_received": 0, "dxy_received": 0, "pairs_formed": 0, "bias_published": 0, "read_loops": 0}
def _debug_log(loc: str, msg: str, data: dict, hyp: str) -> None:
    try:
        os.makedirs(os.path.dirname(_DEBUG_LOG_PATH), exist_ok=True)
        with open(_DEBUG_LOG_PATH, "a") as f:
            f.write(json.dumps({"location": loc, "message": msg, "data": data, "timestamp": int(_time_module.time() * 1000), "sessionId": "debug-session", "hypothesisId": hyp}) + "\n")
    except: pass
# #endregion

# Load configuration
config = HTFBiasConfig()

# Global shutdown event
shutdown_event = asyncio.Event()


async def warmup_processor(
    processor: HTFBiasProcessor,
    repository: BiasRepository,
) -> None:
    """Warmup processor by replaying recent candles from database.
    
    Args:
        processor: HTF bias processor to warmup
        repository: Repository to load candles from
    """
    if not config.enable_warmup:
        logger.info("Warmup disabled for HTF bias processor")
        return
    
    logger.info("Starting warmup for HTF bias processor...")
    
    try:
        # Load recent candles
        candle_pairs = await repository.load_recent_candles(
            count=config.warmup_candles,
        )
        
        if not candle_pairs:
            logger.warning("No candles found for warmup")
            return
        
        logger.info(f"Loaded {len(candle_pairs)} candle pairs for warmup")
        
        # Replay through processor
        for gc_candle, dxy_candle in candle_pairs:
            # Process returns None until sufficient data accumulated
            processor.process(gc_candle, dxy_candle)
        
        logger.info("Warmup complete for HTF bias processor")
    
    except Exception as e:
        logger.error(f"Warmup failed: {e}", exc_info=True)
        # Continue without warmup


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
    
    # Warmup processor
    await warmup_processor(processor, repository)
    
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
                gc_first_ts = str(gc_candles[0].timestamp) if gc_candles else None
                gc_last_ts = str(gc_candles[-1].timestamp) if gc_candles else None
                dxy_first_ts = str(dxy_candles[0].timestamp) if dxy_candles else None
                dxy_last_ts = str(dxy_candles[-1].timestamp) if dxy_candles else None
                _debug_log("htf:main.py:read", "candles_received", {
                    "gc": len(gc_candles), "dxy": len(dxy_candles),
                    "gc_total": _DEBUG_COUNTERS["gc_received"], "dxy_total": _DEBUG_COUNTERS["dxy_received"],
                    "gc_read_ms": int(gc_read_time * 1000), "dxy_read_ms": int(dxy_read_time * 1000),
                    "gc_first": gc_first_ts, "gc_last": gc_last_ts,
                    "dxy_first": dxy_first_ts, "dxy_last": dxy_last_ts,
                    "loop": _DEBUG_COUNTERS["read_loops"]
                }, "B")
            # #endregion
            
            # Sort all candles by timestamp to prevent cleanup from dropping
            # unpaired candles during high-speed replay
            all_candles = list(gc_candles) + list(dxy_candles)
            all_candles.sort(key=lambda c: c.timestamp)
            
            # Add to synchronizer
            for candle in all_candles:
                pair = synchronizer.add_candle(candle)
                if pair:
                    # #region agent log
                    _DEBUG_COUNTERS["pairs_formed"] += 1
                    _debug_log("htf:main.py:pair", "candle_pair_formed", {"timestamp": str(pair[0].timestamp), "total_pairs": _DEBUG_COUNTERS["pairs_formed"]}, "B")
                    # #endregion
                    await process_candle_pair(
                        pair,
                        processor,
                        publisher,
                        repository,
                    )
            
            # #region agent log
            total_loop_time = _time_module.time() - loop_start
            if total_loop_time > 0.5 or _DEBUG_COUNTERS["read_loops"] % 100 == 0:  # Log every 100 loops or slow loops
                _debug_log("htf:main.py:loop", "loop_completed", {
                    "loop": _DEBUG_COUNTERS["read_loops"],
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
    
    # Process through HTF bias calculator
    bias = processor.process(gc_candle, dxy_candle)
    
    # Only publish and persist if bias was computed (at HTF boundary)
    if bias is not None:
        # #region agent log
        _DEBUG_COUNTERS["bias_published"] += 1
        _debug_log("htf:main.py:publish", "bias_published", {"bias": bias.bias, "score": bias.score, "confidence": bias.confidence, "structure_1h": bias.structure_1h, "structure_15m": bias.structure_15m, "timestamp": str(gc_candle.timestamp), "total": _DEBUG_COUNTERS["bias_published"]}, "B")
        # #endregion
        # Publish to Redis stream
        await publisher.publish(bias)
        
        # Persist to database
        await repository.save_bias(bias)
        
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
    
    # Start processing task
    processing_task = asyncio.create_task(
        process_candles(redis_client, db_pool)
    )
    
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)

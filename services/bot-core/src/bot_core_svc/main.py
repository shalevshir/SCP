"""Bot Core Service main entry point."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from scp_shared.common import get_logger, mask_connection_url
from scp_shared.database import DatabasePool
from scp_shared.health import create_health_router
from scp_shared.messaging import RedisStreamConsumer
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage

from bot_core_svc.bias_cache import HTFBiasCache
from bot_core_svc.config import BotCoreConfig
from bot_core_svc.guardrails import GuardrailsService
from bot_core_svc.publisher import SignalPublisher
from bot_core_svc.session import SessionValidationService
from bot_core_svc.signal_engine import SignalEngine
from bot_core_svc.state_repository import StateRepository

# Configure basic logging before anything else
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = get_logger(__name__)

# #region agent log
import os
_DEBUG_LOG_PATH = os.environ.get("DEBUG_LOG_PATH", "/Users/shalev/Code/SCP/.cursor/debug.log")
_DEBUG_COUNTERS = {"features_received": 0, "bias_received": 0, "session_blocked": 0, "guardrails_blocked": 0, "signals_generated": 0}
def _debug_log(loc: str, msg: str, data: dict, hyp: str) -> None:
    try:
        import time
        os.makedirs(os.path.dirname(_DEBUG_LOG_PATH), exist_ok=True)
        with open(_DEBUG_LOG_PATH, "a") as f:
            f.write(json.dumps({"location": loc, "message": msg, "data": data, "timestamp": int(time.time() * 1000), "sessionId": "debug-session", "hypothesisId": hyp}) + "\n")
    except: pass
# #endregion

# Load configuration
config = BotCoreConfig()

# Global shutdown event
shutdown_event = asyncio.Event()


async def process_features(
    redis_client: redis.Redis,
    db_pool: DatabasePool,
) -> None:
    """Main processing loop: consume features, generate signals, publish.
    
    Args:
        redis_client: Redis client
        db_pool: Database pool
    """
    logger.info("Starting feature processing loop")
    
    # Initialize components
    # max_history=2000 to cover multi-day replays (6 days @ 15-min intervals = ~576 entries)
    bias_cache = HTFBiasCache(ttl_seconds=config.bias_cache_ttl_seconds, max_history=2000)
    signal_engine = SignalEngine()
    signal_publisher = SignalPublisher(redis_client)
    session_service = SessionValidationService(config_path=config.session_config_path)
    # StateRepository needs the trading timezone to match SessionValidator's date calculation
    state_repo = StateRepository(
        db_pool,
        trading_timezone=session_service.config.timezone,
    )
    guardrails_service = GuardrailsService(state_repo)
    
    # Load daily state
    await guardrails_service.load_state()
    
    # Create consumers
    features_consumer = RedisStreamConsumer(
        redis_client,
        stream="features.1m",
        group="bot-core",
        consumer_name="instance-1",
        message_type=FeaturesMessage,
    )
    
    bias_consumer = RedisStreamConsumer(
        redis_client,
        stream="htf.bias",
        group="bot-core",
        consumer_name="instance-1",
        message_type=HTFBiasMessage,
    )
    
    logger.info("Bot Core Service ready - consuming features and bias")
    
    try:
        while not shutdown_event.is_set():
            # Read from both streams
            features_list = await features_consumer.read(count=10, block_ms=1000)
            bias_list = await bias_consumer.read(count=10, block_ms=1000)
            
            # #region agent log
            _DEBUG_COUNTERS["features_received"] += len(features_list)
            _DEBUG_COUNTERS["bias_received"] += len(bias_list)
            if features_list or bias_list:
                _debug_log("bc:main.py:read", "streams_read", {"features": len(features_list), "bias": len(bias_list), "total_features": _DEBUG_COUNTERS["features_received"], "total_bias": _DEBUG_COUNTERS["bias_received"]}, "C")
            # #endregion
            
            # Update bias cache
            for bias_msg in bias_list:
                bias_cache.update(bias_msg)
                # #region agent log
                _debug_log("bc:main.py:bias", "bias_cached", {"bias": bias_msg.bias, "score": bias_msg.score, "confidence": bias_msg.confidence, "timestamp": str(bias_msg.timestamp)}, "B")
                # #endregion
                logger.debug(
                    f"Updated bias cache: {bias_msg.bias} "
                    f"(score: {bias_msg.score:.1f}, confidence: {bias_msg.confidence})"
                )
            
            # Process features
            for features_msg in features_list:
                await process_feature_message(
                    features_msg,
                    bias_cache,
                    signal_engine,
                    signal_publisher,
                    guardrails_service,
                    session_service,
                )
    
    except asyncio.CancelledError:
        logger.info("Feature processing cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in feature processing loop: {e}", exc_info=True)
        raise


async def process_feature_message(
    features: FeaturesMessage,
    bias_cache: HTFBiasCache,
    signal_engine: SignalEngine,
    signal_publisher: SignalPublisher,
    guardrails_service: GuardrailsService,
    session_service: SessionValidationService,
) -> None:
    """Process a single feature message.
    
    Args:
        features: Features message
        bias_cache: Bias cache
        signal_engine: Signal engine
        signal_publisher: Signal publisher
        guardrails_service: Guardrails service
        session_service: Session validation service
    """
    # 1. Validate session
    session_result = session_service.evaluate(features.timestamp)
    if not session_result.session_ok:
        # #region agent log
        _DEBUG_COUNTERS["session_blocked"] += 1
        _debug_log("bc:main.py:session", "session_blocked", {"timestamp": str(features.timestamp), "reason": session_result.reason, "total_blocked": _DEBUG_COUNTERS["session_blocked"]}, "C")
        # #endregion
        logger.debug(
            f"Session blocked at {features.timestamp}: {session_result.reason}"
        )
        return
    
    # 2. Check guardrails
    guardrail_result = guardrails_service.evaluate(session_result.constraints)
    if not guardrail_result.allowed:
        # #region agent log
        _DEBUG_COUNTERS["guardrails_blocked"] += 1
        _debug_log("bc:main.py:guardrails", "guardrails_blocked", {"timestamp": str(features.timestamp), "reasons": guardrail_result.reasons, "total_blocked": _DEBUG_COUNTERS["guardrails_blocked"]}, "C")
        # #endregion
        logger.debug(
            f"Guardrails blocked at {features.timestamp}: {guardrail_result.reasons}"
        )
        return
    
    # 3. Get bias for this feature's timestamp (critical for replay mode)
    # Uses timestamp-aware lookup to ensure features are evaluated with
    # the correct historical bias, not a future bias that arrived earlier
    bias = bias_cache.get_for_timestamp_or_default(features.timestamp)
    
    # #region agent log
    _debug_log("bc:main.py:signal_check", "checking_signal", {"timestamp": str(features.timestamp), "close": features.close, "vwap": features.vwap, "bias": bias.bias, "bias_score": bias.score, "bias_ts": str(bias.timestamp)}, "D")
    # #endregion
    
    # 4. Build context
    context = {
        "session_ok": True,
        "enforcer_tier": config.enforcer_tier,
    }
    
    # 5. Generate signal
    signal_msg = signal_engine.generate(features, bias, context)
    
    # 6. Publish A+ signals
    if signal_msg is not None:
        # #region agent log
        _DEBUG_COUNTERS["signals_generated"] += 1
        _debug_log("bc:main.py:signal", "signal_generated", {"id": signal_msg.id, "direction": signal_msg.direction, "setup": signal_msg.setup_type, "score": signal_msg.score, "confidence": signal_msg.confidence, "total": _DEBUG_COUNTERS["signals_generated"]}, "D")
        # #endregion
        await signal_publisher.publish(signal_msg)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    logger.info(f"Starting Bot Core Service v{config.service_version}")
    
    # Startup
    redis_client = redis.Redis.from_url(config.redis_url)
    logger.info(f"Connected to Redis at {mask_connection_url(config.redis_url)}")
    
    db_pool = DatabasePool(config.database_url)
    await db_pool.connect()
    logger.info(f"Connected to database at {mask_connection_url(config.database_url)}")
    
    # Start processing task
    processing_task = asyncio.create_task(
        process_features(redis_client, db_pool)
    )
    
    yield
    
    # Shutdown
    logger.info("Shutting down Bot Core Service")
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
        logger.info("Bot Core Service stopped")


# Create FastAPI app
app = FastAPI(
    title="SCP Bot Core Service",
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
    uvicorn.run(app, host="0.0.0.0", port=8004)

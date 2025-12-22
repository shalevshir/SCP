"""Bot Core Service main entry point."""

import asyncio
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
    bias_cache = HTFBiasCache(ttl_seconds=config.bias_cache_ttl_seconds)
    signal_engine = SignalEngine()
    signal_publisher = SignalPublisher(redis_client)
    state_repo = StateRepository(db_pool)
    guardrails_service = GuardrailsService(state_repo)
    session_service = SessionValidationService(config_path=config.session_config_path)
    
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
            
            # Update bias cache
            for bias_msg in bias_list:
                bias_cache.update(bias_msg)
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
        logger.debug(
            f"Session blocked at {features.timestamp}: {session_result.reason}"
        )
        return
    
    # 2. Check guardrails
    guardrail_result = guardrails_service.evaluate(session_result.constraints)
    if not guardrail_result.allowed:
        logger.debug(
            f"Guardrails blocked at {features.timestamp}: {guardrail_result.reasons}"
        )
        return
    
    # 3. Get bias (or default neutral)
    bias = bias_cache.get_or_default()
    
    # 4. Build context
    context = {
        "session_ok": True,
        "enforcer_tier": config.enforcer_tier,
    }
    
    # 5. Generate signal
    signal_msg = signal_engine.generate(features, bias, context)
    
    # 6. Publish A+ signals
    if signal_msg is not None:
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

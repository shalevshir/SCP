"""Bot Core Service main entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

import redis.asyncio as redis
from fastapi import FastAPI
from scp_shared.admin import KillSwitchRepository
from scp_shared.alerts import AlertLevel, AlertType, send_alert
from scp_shared.common import get_logger, mask_connection_url
from scp_shared.database import DatabasePool
from scp_shared.health import create_health_router
from scp_shared.messaging import RedisStreamConsumer
from scp_shared.messaging.schemas import FeaturesMessage, HTFBiasMessage
from scp_shared.metrics import create_metrics_router

from bot_core_svc import metrics as core_metrics
from bot_core_svc.active_trade_checker import ActiveTradeChecker
from bot_core_svc.bias_cache import HTFBiasCache
from bot_core_svc.config import BotCoreConfig
from bot_core_svc.guardrails import GuardrailsService
from bot_core_svc.publisher import SignalPublisher
from bot_core_svc.session import SessionValidationService
from bot_core_svc.signal_engine import SignalEngine
from bot_core_svc.signal_repository import SignalRepository
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

# Global kill switch state (populated in lifespan)
_kill_switch_repo: KillSwitchRepository | None = None
_is_killed: bool = False


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
    # max_history=2000 to cover multi-day replays (6d @ 15min = ~576)
    bias_cache = HTFBiasCache(
        ttl_seconds=config.bias_cache_ttl_seconds, max_history=2000
    )
    signal_engine = SignalEngine(
        service_mode=config.service_mode,
        service_name=config.service_name,
    )
    signal_publisher = SignalPublisher(redis_client)
    signal_repository = SignalRepository(db_pool)
    session_service = SessionValidationService(
        config_path=config.session_config_path
    )
    # StateRepository needs trading timezone to match SessionValidator
    state_repo = StateRepository(
        db_pool,
        trading_timezone=session_service.config.timezone,
    )
    guardrails_service = GuardrailsService(state_repo)
    # Active trade checker - matches backtest blocking when trade active
    active_trade_checker = ActiveTradeChecker(db_pool, max_active_trades=1)
    
    # Load daily state
    await guardrails_service.load_state()
    
    # Warmup period tracking
    warmup_bar_count = 0
    logger.info(
        f"Warmup period: {config.warmup_bars} bars "
        f"(signal generation disabled during warmup)"
    )
    
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
                warmup_bar_count = await process_feature_message(
                    features_msg,
                    bias_cache,
                    signal_engine,
                    signal_publisher,
                    signal_repository,
                    guardrails_service,
                    session_service,
                    active_trade_checker,
                    warmup_bar_count,
                    config.warmup_bars,
                )
    
    except asyncio.CancelledError:
        logger.info("Feature processing cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in feature processing loop: {e}", exc_info=True)
        send_alert(
            AlertLevel.CRITICAL,
            AlertType.SERVICE_CRASHED,
            f"Bot Core Service crashed: {e}",
            context={
                "service": "bot-core",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "timestamp": datetime.now().isoformat(),
            },
        )
        raise


async def process_feature_message(
    features: FeaturesMessage,
    bias_cache: HTFBiasCache,
    signal_engine: SignalEngine,
    signal_publisher: SignalPublisher,
    signal_repository: SignalRepository,
    guardrails_service: GuardrailsService,
    session_service: SessionValidationService,
    active_trade_checker: ActiveTradeChecker,
    warmup_bar_count: int,
    warmup_bars: int,
) -> int:
    """Process a single feature message.
    
    Args:
        features: Features message
        bias_cache: Bias cache
        signal_engine: Signal engine
        signal_publisher: Signal publisher
        signal_repository: Signal repository for persisting all signals
        guardrails_service: Guardrails service
        session_service: Session validation service
        active_trade_checker: Active trade checker (matches backtest behavior)
        warmup_bar_count: Current bar count (for warmup tracking)
        warmup_bars: Number of bars to skip during warmup
        
    Returns:
        Updated warmup_bar_count
    """
    global _is_killed
    
    # Get metric labels
    mode = config.service_mode
    service = config.service_name
    
    # Increment bar counter
    warmup_bar_count += 1
    
    
    # KILL SWITCH: Skip signal generation if killed
    if _is_killed:
        logger.debug(
            f"🚨 Kill switch active - skipping signal generation "
            f"at {features.timestamp}"
        )
        # METRIC: Track rejection
        core_metrics.record_signal_rejection("kill_switch", mode, service)
        return warmup_bar_count
    
    # Check warmup period
    if warmup_bar_count <= warmup_bars:
        logger.debug(
            f"Warmup: bar {warmup_bar_count}/{warmup_bars} - skipping signal generation"
        )
        # METRIC: Track rejection
        core_metrics.record_signal_rejection("warmup", mode, service)
        return warmup_bar_count
    
    # 1. Validate session
    session_result = session_service.evaluate(features.timestamp)
    
    # METRIC: Update session validity for trader dashboard
    session_valid_value = 1.0 if session_result.session_ok else 0.0
    core_metrics.session_valid.labels(mode=mode, service=service).set(
        session_valid_value
    )
    
    if not session_result.session_ok:
        logger.debug(
            f"Session blocked at {features.timestamp}: {session_result.reason}"
        )
        # METRIC: Track rejection
        core_metrics.record_signal_rejection("session_filter", mode, service)
        return warmup_bar_count
    
    # 2. Check guardrails
    guardrail_result = guardrails_service.evaluate(session_result.constraints)
    if not guardrail_result.allowed:
        logger.debug(
            f"Guardrails blocked at {features.timestamp}: {guardrail_result.reasons}"
        )
        # METRIC: Track rejection (use risk_limit as the general category)
        core_metrics.record_signal_rejection("risk_limit", mode, service)
        return warmup_bar_count
    
    # 2.5. Check DXY availability (required for accurate scoring)
    if features.dxy_correlation is None and features.dxy_corr is None:
        logger.debug(
            f"DXY data unavailable at {features.timestamp} "
            f"- skipping signal generation"
        )
        # METRIC: Track rejection
        core_metrics.record_signal_rejection("invalid_context", mode, service)
        return warmup_bar_count
    
    # 2.6. CRITICAL: Check if active trade exists (matches backtest)
    # Backtest blocks signal generation when active trades >= max_concurrent
    can_trade, active_count = await active_trade_checker.can_take_new_trade()
    if not can_trade:
        logger.debug(
            f"Signal blocked at {features.timestamp}: "
            f"active trade exists ({active_count} active)"
        )
        # METRIC: Track rejection
        core_metrics.record_signal_rejection("active_trade", mode, service)
        return warmup_bar_count
    
    # 3. Get bias for this feature's timestamp (critical for replay mode)
    # Uses timestamp-aware lookup to ensure features are evaluated with
    # the correct historical bias, not a future bias that arrived earlier
    bias = bias_cache.get_for_timestamp_or_default(features.timestamp)
    
    # 4. Build context
    context = {
        "session_ok": True,
        "enforcer_tier": config.enforcer_tier,
    }
    
    # 5. Generate signal (with timing)
    timer = core_metrics.signal_generation_seconds.labels(
        mode=mode, service=service
    )
    with timer.time():
        result = signal_engine.generate(features, bias, context)
    
    # 6. Save ALL signals (approved and rejected) to signal_history
    try:
        await signal_repository.save_signal(
            signal=result.raw_signal,
            features=features,
            htf_bias=bias,
            was_approved=(result.signal_msg is not None),
            rejection_stage=result.rejection_reason,
            signal_message_id=result.signal_msg.id if result.signal_msg else None,
        )
    except Exception as e:
        # Log error but don't block signal publication
        logger.error(f"Failed to save signal to history: {e}", exc_info=True)
    
    # 7. Publish A+ signals
    if result.signal_msg is not None:
        await signal_publisher.publish(result.signal_msg)
        
        # METRIC: Track signal generated
        core_metrics.signals_generated_total.labels(
            mode=mode,
            service=service,
            setup_type=result.signal_msg.setup_type,
            timeframe=features.timeframe,
        ).inc()
        
        # METRIC: Update current setup type for trader dashboard
        setup_type_value = core_metrics.SETUP_TYPE_ENCODING.get(
            result.signal_msg.setup_type, 0.0
        )
        core_metrics.current_setup_type.labels(
            mode=mode, service=service
        ).set(setup_type_value)
        
    else:
        # Signal was rejected - record the specific reason
        # rejection_reason: htf_validity, confidence_filter, neutral, tp_val
        if result.rejection_reason:
            core_metrics.record_signal_rejection(
                result.rejection_reason, mode, service
            )
        
        # METRIC: Clear setup type when no signal generated
        core_metrics.current_setup_type.labels(
            mode=mode, service=service
        ).set(0.0)
        
    
    return warmup_bar_count


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    global _kill_switch_repo, _is_killed
    
    logger.info(f"Starting Bot Core Service v{config.service_version}")
    
    # Startup
    redis_client = redis.Redis.from_url(config.redis_url)
    logger.info(f"Connected to Redis at {mask_connection_url(config.redis_url)}")
    
    db_pool = DatabasePool(config.database_url)
    await db_pool.connect()
    logger.info(f"Connected to database at {mask_connection_url(config.database_url)}")
    
    # Initialize kill switch repository and load state
    _kill_switch_repo = KillSwitchRepository(db_pool)
    kill_state = await _kill_switch_repo.get_state("bot-core")
    _is_killed = kill_state.is_killed
    if _is_killed:
        logger.warning(
            f"🚨 KILL SWITCH IS ACTIVE - Signal generation halted "
            f"(killed at {kill_state.killed_at} by {kill_state.killed_by}: "
            f"{kill_state.reason})"
        )
    else:
        logger.info("✅ Kill switch inactive - Signal generation enabled")
    
    # Set enforcer tier metric
    mode = config.service_mode
    service = config.service_name
    tier_value = core_metrics.ENFORCER_TIER_MAP.get(config.enforcer_tier, 1.0)
    core_metrics.enforcer_tier.labels(mode=mode, service=service).set(tier_value)
    logger.info(f"Enforcer tier: {config.enforcer_tier} (metric value: {tier_value})")
    
    # Initialize session and setup type metrics with defaults
    core_metrics.session_valid.labels(mode=mode, service=service).set(0.0)
    core_metrics.current_setup_type.labels(mode=mode, service=service).set(0.0)
    core_metrics.signal_score.labels(mode=mode, service=service).set(0.0)
    logger.info("Initialized session/setup metrics with default values")
    
    # Send service started alert
    send_alert(
        AlertLevel.INFO,
        AlertType.SERVICE_STARTED,
        f"Bot Core Service v{config.service_version} started",
        context={
            "service": config.service_name,
            "version": config.service_version,
            "kill_switch_active": _is_killed,
            "warmup_bars": config.warmup_bars,
            "enforcer_tier": config.enforcer_tier,
            "timestamp": datetime.now().isoformat(),
        },
    )
    
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

# Add metrics endpoint
metrics_router = create_metrics_router()
app.include_router(metrics_router)


@app.post("/admin/kill")
async def kill_switch(reason: str = "Manual kill via API") -> dict[str, str]:
    """Activate kill switch to halt all signal generation.
    
    When activated:
    - Signal generation is halted
    - Feature consumption continues (to stay in sync)
    - State persists across restarts
    
    Args:
        reason: Reason for activation
        
    Returns:
        Status message with kill state
    """
    global _kill_switch_repo, _is_killed
    
    if _kill_switch_repo is None:
        return {"status": "error", "message": "Service not fully initialized"}
    
    await _kill_switch_repo.set_killed("bot-core", "admin", reason)
    _is_killed = True
    
    logger.warning(f"🚨 KILL SWITCH ACTIVATED: {reason}")
    send_alert(
        AlertLevel.CRITICAL,
        AlertType.KILL_SWITCH_ACTIVATED,
        f"Bot Core Service kill switch activated: {reason}",
        context={
            "service": "bot-core",
            "killed_by": "admin",
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        },
    )
    
    return {
        "status": "killed",
        "message": f"Signal generation halted: {reason}",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/admin/resume")
async def resume_trading() -> dict[str, str]:
    """Deactivate kill switch to resume signal generation.
    
    Returns:
        Status message
    """
    global _kill_switch_repo, _is_killed
    
    if _kill_switch_repo is None:
        return {"status": "error", "message": "Service not fully initialized"}
    
    await _kill_switch_repo.set_resumed("bot-core")
    _is_killed = False
    
    logger.info("✅ Kill switch deactivated - Signal generation resumed")
    send_alert(
        AlertLevel.INFO,
        AlertType.KILL_SWITCH_RESUMED,
        "Bot Core Service kill switch deactivated - signal generation resumed",
        context={
            "service": "bot-core",
            "resumed_by": "admin",
            "timestamp": datetime.now().isoformat(),
        },
    )
    
    return {
        "status": "active",
        "message": "Signal generation resumed",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/admin/status")
async def get_status() -> dict:
    """Get current kill switch status.
    
    Returns:
        Current kill switch state
    """
    global _kill_switch_repo, _is_killed
    
    if _kill_switch_repo is None:
        return {"status": "error", "message": "Service not fully initialized"}
    
    kill_state = await _kill_switch_repo.get_state("bot-core")
    
    return {
        "service": "bot-core",
        "is_killed": kill_state.is_killed,
        "killed_at": kill_state.killed_at.isoformat() if kill_state.killed_at else None,
        "killed_by": kill_state.killed_by,
        "reason": kill_state.reason,
        "updated_at": kill_state.updated_at.isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)

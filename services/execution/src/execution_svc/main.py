"""Execution Service main entry point."""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI

from scp_shared.common import get_logger, mask_connection_url
from scp_shared.database import DatabasePool
from scp_shared.health import create_health_router
from scp_shared.messaging import RedisStreamConsumer, CandleFeatureSynchronizer
from scp_shared.messaging.schemas import CandleMessage, FeaturesMessage, SignalMessage

from execution_svc.broker import PaperBroker
from execution_svc.config import ExecutionConfig
from execution_svc.state_machine_manager import StateMachineManager
from execution_svc.trade_manager import TradeManager
from execution_svc.trade_publisher import TradePublisher
from execution_svc.trade_repository import TradeRepository

# Configure basic logging before anything else
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = get_logger(__name__)

# Load configuration
config = ExecutionConfig()

# Global shutdown event
shutdown_event = asyncio.Event()

# Global references for reset endpoint (populated in process_streams)
_trade_manager: Optional[TradeManager] = None
_broker: Optional[PaperBroker] = None
_sm_manager: Optional[StateMachineManager] = None
_synchronizer: Optional[CandleFeatureSynchronizer] = None


async def process_streams(
    redis_client: redis.Redis,
    db_pool: DatabasePool,
) -> None:
    """Main processing loop: consume signals and candles, manage trades.
    
    Args:
        redis_client: Redis client
        db_pool: Database pool
    """
    global _trade_manager, _broker, _sm_manager
    
    logger.info("Starting execution processing loop")
    
    # Initialize components
    broker = PaperBroker()
    sm_manager = StateMachineManager(db_pool)
    trade_repo = TradeRepository(db_pool)
    trade_publisher = TradePublisher(redis_client)
    trade_manager = TradeManager(
        broker=broker,
        state_machine_manager=sm_manager,
        trade_repository=trade_repo,
        trade_publisher=trade_publisher,
        max_active_trades=config.max_active_trades,
        pdll_limit=config.pdll_limit,
        max_trades_per_day=config.max_trades_per_day,
    )
    
    # Store global references for reset endpoint
    _trade_manager = trade_manager
    _broker = broker
    _sm_manager = sm_manager
    
    # Restore state from database
    await sm_manager.restore_from_db()
    await trade_manager.restore_active_trades()
    
    # Create consumers
    signals_consumer = RedisStreamConsumer(
        redis_client,
        stream="signals.pending",
        group="execution",
        consumer_name="instance-1",
        message_type=SignalMessage,
    )
    
    candles_consumer = RedisStreamConsumer(
        redis_client,
        stream="candles.1m.gc",
        group="execution",
        consumer_name="instance-1",
        message_type=CandleMessage,
    )
    
    features_consumer = RedisStreamConsumer(
        redis_client,
        stream="features.1m",
        group="execution",
        consumer_name="instance-1",
        message_type=FeaturesMessage,
    )
    
    logger.info("Execution Service ready - consuming signals and candles")
    
    # Synchronizer to pair candles with their matching features by timestamp
    # Use a larger timeout (5 minutes of data-time) to handle:
    # 1. High-speed replay where many messages arrive in quick succession
    global _synchronizer  # noqa: PLW0603 - intentional global for reset endpoint
    # 2. Gaps in historical data (e.g., trading hours only)
    # The cleanup uses DATA timestamps, not wall-clock time.
    synchronizer = CandleFeatureSynchronizer(timeout_seconds=300)
    _synchronizer = synchronizer  # Store global reference for reset endpoint
    
    # Cleanup counter (run cleanup every N candles to prevent memory leaks)
    cleanup_counter = 0
    cleanup_interval = 50  # Cleanup every 50 candles (~50 minutes)
    
    try:
        while not shutdown_event.is_set():
            # Read from all streams IN PARALLEL to avoid sequential blocking
            # Previously, each read blocked for up to 1000ms, causing ~3 second
            # delays when streams were empty. Now they run concurrently.
            signals_list, candles_list, features_list = await asyncio.gather(
                signals_consumer.read(count=10, block_ms=100),  # Short timeout for signals
                candles_consumer.read(count=100, block_ms=100),  # Larger batch for replay
                features_consumer.read(count=100, block_ms=100),  # Larger batch for replay
            )
            
            # Process signals (buffer for next bar execution)
            for signal_msg in signals_list:
                await trade_manager.on_signal(signal_msg)
            
            # CRITICAL FIX: Interleave candle and feature processing to prevent
            # cleanup from dropping unpaired messages during high-speed replay.
            # Previously, all candles were added first, then all features.
            # This caused messages spanning >2 minutes (data-time) to be dropped
            # before their pair arrived.
            #
            # New approach: Merge and sort by timestamp to maximize pairing.
            all_messages: list[tuple[str, CandleMessage | FeaturesMessage]] = []
            for c in candles_list:
                all_messages.append(("candle", c))
            for f in features_list:
                all_messages.append(("features", f))
            all_messages.sort(key=lambda x: x[1].timestamp)
            
            for msg_type, msg in all_messages:
                if msg_type == "candle":
                    pair = synchronizer.add_candle(msg)  # type: ignore[arg-type]
                else:
                    pair = synchronizer.add_features(msg)  # type: ignore[arg-type]
                
                if pair:
                    await _process_candle_with_features(pair, trade_manager, sm_manager)
                    cleanup_counter += 1
            
            # Log synchronizer stats periodically for debugging
            stats = synchronizer.get_buffer_stats()
            if stats["total_unpaired"] > 10:
                logger.warning(
                    f"Synchronizer buffer growing: {stats} - "
                    "candles/features may be out of sync"
                )
            
            # Periodic cleanup to prevent memory leaks
            if cleanup_counter >= cleanup_interval:
                sm_manager.cleanup_old_state_machines()
                cleanup_counter = 0
    
    except asyncio.CancelledError:
        logger.info("Execution processing cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in execution processing loop: {e}", exc_info=True)
        raise


async def _process_candle_with_features(
    pair: tuple[CandleMessage, FeaturesMessage],
    trade_manager: TradeManager,
    sm_manager: StateMachineManager,
) -> None:
    """Process a synchronized candle-features pair.
    
    This ensures that when we process a candle, we have the matching
    features with the same timestamp for invalidation checks.
    
    Args:
        pair: Tuple of (candle, features) with matching timestamps
        trade_manager: Trade manager instance
        sm_manager: State machine manager instance
    """
    candle_msg, features_msg = pair
    
    logger.info(f"Processing candle: {candle_msg.timestamp} (with matching features)")
    
    # CRITICAL: Check session reset BEFORE execute_pending_signals
    # to ensure daily limits (PDLL, max trades) are fresh at day boundaries
    trade_manager.check_session_reset(candle_msg.timestamp)
    
    # Increment bar counter BEFORE execute_pending_signals so that
    # check_confirmation() can confirm signals from the previous bar
    # (confirmation requires bar_idx > detection_bar_idx)
    sm_manager.increment_bar_counter()
    
    # Execute pending signals at this candle's open
    await trade_manager.execute_pending_signals(candle_msg.open)
    
    # Monitor active trades for SL/TP and invalidation
    # Now we pass the CORRECT features that match this candle's timestamp
    await trade_manager.on_candle(candle_msg, features_msg)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    logger.info(f"Starting Execution Service v{config.service_version}")
    
    # Startup
    redis_client = redis.Redis.from_url(config.redis_url)
    logger.info(f"Connected to Redis at {mask_connection_url(config.redis_url)}")
    
    db_pool = DatabasePool(config.database_url)
    await db_pool.connect()
    logger.info(f"Connected to database at {mask_connection_url(config.database_url)}")
    
    # Start processing task
    processing_task = asyncio.create_task(
        process_streams(redis_client, db_pool)
    )
    
    yield
    
    # Shutdown
    logger.info("Shutting down Execution Service")
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
        logger.info("Execution Service stopped")


# Create FastAPI app
app = FastAPI(
    title="SCP Execution Service",
    version=config.service_version,
    lifespan=lifespan,
)

# Add health check endpoints
health_router = create_health_router(
    service_name=config.service_name,
    version=config.service_version,
)
app.include_router(health_router)


@app.post("/admin/reset")
async def reset_state() -> dict[str, str]:
    """Reset service state for testing.
    
    Clears all in-memory state:
    - Active trades
    - Pending signals
    - State machines
    - Daily tracker
    - Broker positions
    - Synchronizer buffers
    
    This endpoint is intended for integration testing only.
    
    Returns:
        Status message
    """
    global _trade_manager, _broker, _sm_manager, _synchronizer
    
    if _trade_manager is None or _broker is None or _sm_manager is None:
        return {"status": "error", "message": "Service not fully initialized"}
    
    # Reset trade manager state
    _trade_manager._active_trades.clear()
    _trade_manager._pending_signals.clear()
    _trade_manager._trade_entry_bars.clear()
    _trade_manager._daily_tracker.reset_state()
    
    # Reset state machine manager
    _sm_manager._state_machines.clear()
    _sm_manager._bar_counter = 0
    
    # Reset broker
    _broker.reset_state()
    
    # Reset synchronizer buffers (critical for test isolation)
    if _synchronizer is not None:
        _synchronizer.clear()
    
    logger.info("Execution service state reset via /admin/reset endpoint")
    
    return {"status": "ok", "message": "State reset successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)

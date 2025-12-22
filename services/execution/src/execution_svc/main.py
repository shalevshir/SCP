"""Execution Service main entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from scp_shared.common import get_logger, mask_connection_url
from scp_shared.database import DatabasePool
from scp_shared.health import create_health_router
from scp_shared.messaging import RedisStreamConsumer
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


async def process_streams(
    redis_client: redis.Redis,
    db_pool: DatabasePool,
) -> None:
    """Main processing loop: consume signals and candles, manage trades.
    
    Args:
        redis_client: Redis client
        db_pool: Database pool
    """
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
    
    # Cache latest features for invalidation checking
    latest_features: FeaturesMessage | None = None
    
    # Cleanup counter (run cleanup every N candles to prevent memory leaks)
    cleanup_counter = 0
    cleanup_interval = 50  # Cleanup every 50 candles (~50 minutes)
    
    try:
        while not shutdown_event.is_set():
            # Read from all streams
            signals_list = await signals_consumer.read(count=10, block_ms=1000)
            candles_list = await candles_consumer.read(count=10, block_ms=1000)
            features_list = await features_consumer.read(count=10, block_ms=1000)
            
            # Update features cache
            if features_list:
                latest_features = features_list[-1]  # Keep most recent
            
            # Process signals (buffer for next bar execution)
            for signal_msg in signals_list:
                await trade_manager.on_signal(signal_msg)
            
            # Process candles (check session reset, execute pending signals, monitor SL/TP)
            for candle_msg in candles_list:
                # CRITICAL: Check session reset BEFORE execute_pending_signals
                # to ensure daily limits (PDLL, max trades) are fresh at day boundaries
                trade_manager.check_session_reset(candle_msg.timestamp)
                
                # Execute pending signals at this candle's open
                await trade_manager.execute_pending_signals(candle_msg.open)
                
                # Monitor active trades for SL/TP and invalidation
                await trade_manager.on_candle(candle_msg, latest_features)
                cleanup_counter += 1
            
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)


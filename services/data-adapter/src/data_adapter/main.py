"""Data Adapter Service main entry point."""

import asyncio
from contextlib import asynccontextmanager

import redis.asyncio as redis
from common.logger import get_logger
from fastapi import FastAPI
from scp_shared.health import create_health_router

from data_adapter.candle_aggregator import CandleAggregator
from data_adapter.config import DataAdapterConfig
from data_adapter.databento_client import MockDatabentoClient
from data_adapter.gap_detector import GapDetector
from data_adapter.publisher import CandlePublisher
from data_adapter.session_filter import SessionFilter

logger = get_logger(__name__)

# Load configuration
config = DataAdapterConfig()

# Global shutdown event
shutdown_event = asyncio.Event()


async def consume_ticks(
    client,  # DatabentoClientBase
    gc_aggregator: CandleAggregator,
    dxy_aggregator: CandleAggregator,
    gap_detector: GapDetector,
    session_filter: SessionFilter,
    publisher: CandlePublisher,
) -> None:
    """Main loop: consume ticks, aggregate, publish.
    
    Args:
        client: Databento client (real or mock)
        gc_aggregator: Gold candle aggregator
        dxy_aggregator: DXY candle aggregator
        gap_detector: Gap detector
        session_filter: Session hour filter
        publisher: Candle publisher
    """
    logger.info("Starting tick consumption loop")
    
    try:
        async for tick in client.stream_ticks():
            # Check for shutdown
            if shutdown_event.is_set():
                logger.info("Shutdown signal received, stopping tick consumption")
                break
            
            # Route to appropriate aggregator
            aggregator = gc_aggregator if tick.symbol == "GC" else dxy_aggregator
            
            # Aggregate tick
            candle = aggregator.update(tick)
            
            if candle is not None:
                logger.debug(
                    f"Candle closed: {candle.symbol} {candle.timestamp} "
                    f"O={candle.open} H={candle.high} L={candle.low} "
                    f"C={candle.close} V={candle.volume}"
                )
                
                # Check for gaps
                has_gap = gap_detector.check_gap(candle)
                if has_gap:
                    logger.warning(
                        f"Gap detected for {candle.symbol}: "
                        f"{gap_detector.gap_start} to {gap_detector.gap_end}"
                    )
                    # TODO: Implement backfill trigger
                    gap_detector.reset()
                
                # Check session hours
                if session_filter.is_trading_hours(candle):
                    # Publish to Redis
                    message_id = await publisher.publish(candle)
                    logger.debug(
                        f"Published candle {candle.symbol} {candle.timestamp}: "
                        f"{message_id}"
                    )
                else:
                    logger.debug(
                        f"Candle outside trading hours, skipping: "
                        f"{candle.timestamp}"
                    )
    
    except asyncio.CancelledError:
        logger.info("Tick consumption cancelled")
        raise
    except Exception as e:
        logger.error(f"Error in tick consumption loop: {e}", exc_info=True)
        raise


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    """Manage application lifecycle."""
    logger.info(f"Starting Data Adapter Service v{config.service_version}")
    
    # Startup
    redis_client = redis.Redis.from_url(config.redis_url)
    logger.info(f"Connected to Redis at {config.redis_url}")
    
    publisher = CandlePublisher(redis_client)
    
    # Initialize aggregators for each symbol
    gc_aggregator = CandleAggregator(symbol="GC", timeframe="1m")
    dxy_aggregator = CandleAggregator(symbol="DXY", timeframe="1m")
    
    # Initialize gap detector
    gap_detector = GapDetector()
    
    # Initialize session filter (disabled by default for testing)
    session_filter = SessionFilter(enabled=False)
    
    # Use mock client for now (replace with real DatabentoClient in production)
    # client = DatabentoClient(api_key=config.databento_api_key, symbols=config.symbols)
    client = MockDatabentoClient()
    
    logger.info("Starting tick consumer task")
    
    # Start tick consumption in background
    consumer_task = asyncio.create_task(
        consume_ticks(
            client,
            gc_aggregator,
            dxy_aggregator,
            gap_detector,
            session_filter,
            publisher,
        )
    )
    
    yield
    
    # Shutdown
    logger.info("Shutting down Data Adapter Service")
    shutdown_event.set()
    consumer_task.cancel()
    
    try:
        await consumer_task
    except asyncio.CancelledError:
        logger.info("Consumer task cancelled successfully")
    except Exception as e:
        logger.error(f"Consumer task failed with exception: {e}", exc_info=True)
    finally:
        # Ensure cleanup happens regardless of how consumer_task ended
        await client.close()
        await redis_client.aclose()
        logger.info("Data Adapter Service stopped")


# Create FastAPI app
app = FastAPI(
    title="SCP Data Adapter Service",
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
    uvicorn.run(app, host="0.0.0.0", port=8001)


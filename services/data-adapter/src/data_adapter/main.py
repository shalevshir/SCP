"""Data Adapter Service main entry point."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import redis.asyncio as redis
from fastapi import FastAPI
from scp_shared.common import get_logger, mask_connection_url
from scp_shared.health import create_health_router
from scp_shared.metrics import create_metrics_router

from data_adapter.candle_aggregator import CandleAggregator
from data_adapter.config import DataAdapterConfig
from data_adapter.databento_client import (
    DatabentoClient,
    DatabentoHistoricalFetcher,
    DataClientBase,
    MockDatabentoClient,
    ResilientDatabentoClient,
)
from data_adapter.gap_detector import GapDetector
from data_adapter.ib_data_client import IBDataClient, ResilientIBDataClient
from data_adapter import metrics as adapter_metrics
from data_adapter.publisher import CandlePublisher
from data_adapter.session_events import SessionEventPublisher
from data_adapter.session_filter import GoldFuturesSessionFilter, SessionFilter

logger = get_logger(__name__)

# Load configuration
config = DataAdapterConfig()

# Global shutdown event
shutdown_event = asyncio.Event()


def create_data_client(config: DataAdapterConfig) -> DataClientBase:
    """Create appropriate data client based on configuration.

    Args:
        config: Data adapter configuration

    Returns:
        Data client instance (IB, Databento, or Mock)
    """
    provider = config.data_provider.lower()

    if provider == "ib":
        logger.info("Creating ResilientIBDataClient for IB Gateway live data")
        inner_client = IBDataClient(
            host=config.ib_host,
            port=config.ib_port,
            client_id=config.ib_client_id,
            gc_symbol=config.ib_gc_symbol,
            dxy_symbol=config.ib_dxy_symbol,
            market_data_type=config.ib_market_data_type,
        )
        return ResilientIBDataClient(
            inner=inner_client,
            max_retries=config.reconnect_max_retries,
            base_delay=config.reconnect_base_delay,
            max_delay=config.reconnect_max_delay,
        )

    elif provider == "databento":
        if not config.databento_api_key:
            logger.error("Databento provider selected but no API key provided")
            raise ValueError("DATABENTO_API_KEY required for databento provider")

        logger.info("Creating ResilientDatabentoClient for live data")
        inner_client = DatabentoClient(
            api_key=config.databento_api_key,
            dataset=config.databento_dataset,
            gc_symbol=config.databento_gc_symbol,
            dxy_symbol=config.databento_dxy_symbol,
        )
        return ResilientDatabentoClient(
            inner=inner_client,
            max_retries=config.reconnect_max_retries,
            base_delay=config.reconnect_base_delay,
            max_delay=config.reconnect_max_delay,
        )

    else:  # mock or any other value
        logger.info(f"Using MockDatabentoClient (provider: {provider})")
        return MockDatabentoClient()


def create_historical_fetcher(config: DataAdapterConfig):
    """Create appropriate historical fetcher based on configuration.

    Args:
        config: Data adapter configuration

    Returns:
        Historical fetcher instance or None
    """
    if not config.gap_backfill_enabled:
        logger.info("Gap backfill disabled")
        return None

    provider = config.data_provider.lower()

    if provider == "databento":
        if not config.databento_api_key:
            logger.warning("Gap backfill enabled but no Databento API key")
            return None

        return DatabentoHistoricalFetcher(
            api_key=config.databento_api_key,
            dataset=config.databento_dataset,
        )

    elif provider == "ib":
        from data_adapter.ib_historical_fetcher import IBHistoricalFetcher

        return IBHistoricalFetcher(
            host=config.ib_host,
            port=config.ib_port,
            client_id=config.ib_client_id + 1,  # Use different client ID (11 if streaming is 10)
            market_data_type=config.ib_market_data_type,
        )

    else:
        logger.info("Mock provider - no historical fetcher")
        return None


async def consume_ticks(
    client,  # DatabentoClientBase
    gc_aggregator: CandleAggregator,
    dxy_aggregator: CandleAggregator,
    gap_detector: GapDetector,
    session_filter: SessionFilter,
    publisher: CandlePublisher,
    session_event_publisher: SessionEventPublisher,
) -> None:
    """Main loop: consume ticks, aggregate, publish.

    Args:
        client: Databento client (real or mock)
        gc_aggregator: Gold candle aggregator
        dxy_aggregator: DXY candle aggregator
        gap_detector: Gap detector
        session_filter: Session hour filter
        publisher: Candle publisher
        session_event_publisher: Session event publisher for open/close events
    """
    logger.info("Starting tick consumption loop")

    # Get metric labels
    mode = config.service_mode
    service = config.service_name

    try:
        async for tick in client.stream_ticks():
            # Check for shutdown
            if shutdown_event.is_set():
                logger.info("Shutdown signal received, stopping tick consumption")
                break

            # METRIC: Count ticks received
            adapter_metrics.market_ticks_total.labels(
                mode=mode, service=service, symbol=tick.symbol
            ).inc()

            # Update tick timestamp for lag calculation
            adapter_metrics.update_tick_timestamp(tick.symbol, tick.timestamp)

            # Route to appropriate aggregator
            aggregator = gc_aggregator if tick.symbol == "GC" else dxy_aggregator

            # Aggregate tick (with timing)
            with adapter_metrics.tick_processing_seconds.labels(
                mode=mode, service=service, symbol=tick.symbol
            ).time():
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

                    # METRIC: Count gap detections
                    adapter_metrics.data_gaps_detected_total.labels(
                        mode=mode, service=service, symbol=candle.symbol
                    ).inc()

                    # Trigger backfill if enabled
                    if config.gap_backfill_enabled:
                        try:
                            backfilled = await gap_detector.backfill(candle.symbol)
                            logger.info(
                                f"Backfilled {len(backfilled)} candles "
                                f"for {candle.symbol}"
                            )

                            # METRIC: Count successful backfills
                            adapter_metrics.gap_backfills_total.labels(
                                mode=mode, service=service, symbol=candle.symbol
                            ).inc()

                            # Publish backfilled candles
                            for bf_candle in backfilled:
                                if session_filter.is_trading_hours(bf_candle):
                                    await publisher.publish(bf_candle)
                                    # METRIC: Count backfilled candles published
                                    adapter_metrics.bars_emitted_total.labels(
                                        mode=mode,
                                        service=service,
                                        symbol=bf_candle.symbol,
                                        timeframe=bf_candle.timeframe,
                                    ).inc()
                        except Exception as e:
                            logger.error(f"Backfill failed for {candle.symbol}: {e}")

                    gap_detector.reset()

                # Check for session state transitions and emit events
                await session_event_publisher.check_and_emit(candle, session_filter)

                # Check session hours
                if session_filter.is_trading_hours(candle):
                    # Publish to Redis
                    message_id = await publisher.publish(candle)
                    logger.debug(
                        f"Published candle {candle.symbol} {candle.timestamp}: "
                        f"{message_id}"
                    )

                    # METRIC: Count candles published
                    adapter_metrics.bars_emitted_total.labels(
                        mode=mode,
                        service=service,
                        symbol=candle.symbol,
                        timeframe=candle.timeframe,
                    ).inc()
                else:
                    logger.debug(
                        f"Candle outside trading hours, skipping: "
                        f"{candle.timestamp}"
                    )

            # METRIC: Update lag metrics periodically (every 100 ticks)
            # Note: This is a simple heuristic to avoid calling datetime.now() on every tick
            try:
                tick_count = adapter_metrics.market_ticks_total.labels(
                    mode=mode, service=service, symbol=tick.symbol
                )._value.get()
                if tick_count % 100 == 0:
                    adapter_metrics.update_lag_metrics(datetime.now(UTC), mode, service)
            except Exception:
                # Silently ignore metric update errors to avoid disrupting data flow
                pass

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
    logger.info(f"Connected to Redis at {mask_connection_url(config.redis_url)}")

    publisher = CandlePublisher(redis_client)

    # Initialize aggregators for each symbol
    gc_aggregator = CandleAggregator(symbol="GC", timeframe="1m")
    dxy_aggregator = CandleAggregator(symbol="DXY", timeframe="1m")

    # Initialize historical fetcher for gap backfill
    historical_fetcher = create_historical_fetcher(config)
    if historical_fetcher:
        logger.info(f"Historical backfill enabled ({config.data_provider})")

    # Initialize gap detector with optional historical fetcher
    gap_detector = GapDetector(historical_fetcher=historical_fetcher)

    # Initialize session filter (use GoldFuturesSessionFilter for proper market hours)
    session_filter = GoldFuturesSessionFilter(enabled=config.session_filter_enabled)

    # Initialize session event publisher
    session_event_publisher = SessionEventPublisher(redis_client)

    # Create data client based on provider configuration
    client = create_data_client(config)

    # METRIC: Set provider connected (assume connected on startup)
    provider = config.data_provider.lower()
    adapter_metrics.data_provider_connected.labels(
        mode=config.service_mode, service=config.service_name, provider=provider
    ).set(1)

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
            session_event_publisher,
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
        # METRIC: Set provider disconnected on shutdown
        adapter_metrics.data_provider_connected.labels(
            mode=config.service_mode, service=config.service_name, provider=provider
        ).set(0)

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

# Add metrics endpoint
metrics_router = create_metrics_router()
app.include_router(metrics_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)

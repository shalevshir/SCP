"""Data Adapter Service main entry point."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import redis.asyncio as redis
from fastapi import FastAPI
from scp_shared.common import get_logger, mask_connection_url
from scp_shared.health import create_health_router
from scp_shared.metrics import create_metrics_router

from data_adapter import metrics as adapter_metrics
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
from data_adapter.ib_historical_fetcher import IBHistoricalFetcher
from data_adapter.publisher import CandlePublisher
from data_adapter.session_events import SessionEventPublisher
from data_adapter.session_filter import GoldFuturesSessionFilter, SessionFilter
from data_adapter.warmup_publisher import WarmupPublisher

logger = get_logger(__name__)

# Load configuration
config = DataAdapterConfig()

# Global shutdown event
shutdown_event = asyncio.Event()


def set_ib_contract_metrics(
    inner_client: IBDataClient, mode: str, service: str
) -> None:
    """Set IB contract info metrics for Grafana display.

    Args:
        inner_client: IBDataClient instance with contract info
        mode: Service mode (dev/test/replay/paper/live)
        service: Service name (data-adapter)
    """
    # Get front month contract info
    gc_month = inner_client._get_front_month("GC")
    dx_month = inner_client._get_front_month("DX")

    # Format contract symbols (e.g., GC -> GCM5 for June 2025)
    # Month codes: F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun,
    #              N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec
    month_codes = {
        1: "F",
        2: "G",
        3: "H",
        4: "J",
        5: "K",
        6: "M",
        7: "N",
        8: "Q",
        9: "U",
        10: "V",
        11: "X",
        12: "Z",
    }

    gc_month_num = int(gc_month[4:6])
    gc_year = gc_month[2:4]
    gc_contract = f"GC{month_codes[gc_month_num]}{gc_year}"

    dx_month_num = int(dx_month[4:6])
    dx_year = dx_month[2:4]
    dx_contract = f"DX{month_codes[dx_month_num]}{dx_year}"

    logger.info(f"IB contracts: GC={gc_contract} ({gc_month}), DXY={dx_contract} ({dx_month})")

    # Set metrics with contract info as labels
    adapter_metrics.ib_contract_info.labels(
        mode=mode, service=service, symbol="GC"
    ).info({"contract": gc_contract, "contract_month": gc_month, "exchange": "COMEX"})

    adapter_metrics.ib_contract_info.labels(
        mode=mode, service=service, symbol="DXY"
    ).info({"contract": dx_contract, "contract_month": dx_month, "exchange": "NYBOT"})


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

        # Set IB contract info metrics for Grafana
        set_ib_contract_metrics(inner_client, config.service_mode, config.service_name)

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
            # Use different client ID (11 if streaming is 10)
            client_id=config.ib_client_id + 1,
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
            # Note: This avoids calling datetime.now() on every tick
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


async def warmup_phase(
    redis_client: redis.Redis,
    historical_fetcher: IBHistoricalFetcher | DatabentoHistoricalFetcher | None,
) -> None:
    """Execute warmup phase: fetch historical data and publish to warmup streams.

    Args:
        redis_client: Redis client for stream publishing
        historical_fetcher: Historical data fetcher (IB or Databento)
    """
    if not config.warmup_enabled:
        logger.info("Warmup disabled - skipping warmup phase")
        return

    if historical_fetcher is None:
        logger.warning("Historical fetcher not available - skipping warmup phase")
        return

    # Only IB historical fetcher supports warmup currently
    if not isinstance(historical_fetcher, IBHistoricalFetcher):
        logger.warning(
            f"Warmup only supported for IB Gateway (current: {type(historical_fetcher).__name__}) - "
            "skipping warmup phase"
        )
        return

    logger.info("Starting warmup phase...")

    try:
        publisher = WarmupPublisher(
            redis_client=redis_client,
            ib_fetcher=historical_fetcher,
            lookback_hours=config.warmup_lookback_hours,
            ttl_seconds=config.warmup_stream_ttl_seconds,
        )

        success = await publisher.publish_warmup_data()

        if success:
            logger.info("Warmup phase complete - warmup streams ready for downstream services")
        else:
            logger.warning(
                "Warmup phase failed - downstream services will fall back to database warmup"
            )

    except Exception as e:
        logger.error(f"Warmup phase failed with exception: {e}", exc_info=True)
        logger.warning("Downstream services will fall back to database warmup")


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

    # Execute warmup phase BEFORE starting live streaming
    # This fetches historical data from IB Gateway and publishes to warmup streams
    # for downstream service initialization
    await warmup_phase(redis_client, historical_fetcher)

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

        # Close historical fetcher if it has a close method (e.g., IB connection)
        if historical_fetcher is not None and hasattr(historical_fetcher, "close"):
            await historical_fetcher.close()

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

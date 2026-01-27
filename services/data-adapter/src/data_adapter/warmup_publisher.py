"""Warmup data publisher - fetches historical data from IB Gateway on startup.

This module provides WarmupPublisher that fetches historical OHLCV data from
IB Gateway and publishes it to ephemeral Redis streams for downstream service
warmup initialization.
"""

from datetime import UTC, datetime, timedelta

import redis.asyncio as redis
from scp_shared.common.logger import get_logger

from data_adapter.ib_historical_fetcher import IBHistoricalFetcher

logger = get_logger(__name__)


class WarmupPublisher:
    """Publishes historical candles to warmup streams on startup.

    Fetches historical data from IB Gateway and publishes to Redis streams
    that downstream services consume for warmup initialization. Streams are
    ephemeral with TTL to auto-expire after consumption.

    Example:
        >>> publisher = WarmupPublisher(
        ...     redis_client=redis_client,
        ...     ib_fetcher=historical_fetcher,
        ...     lookback_hours=24,
        ...     ttl_seconds=600
        ... )
        >>> success = await publisher.publish_warmup_data()
        >>> # success=True if data published, False if IB unavailable
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        ib_fetcher: IBHistoricalFetcher,
        lookback_hours: int = 24,
        ttl_seconds: int = 600,
    ):
        """Initialize warmup publisher.

        Args:
            redis_client: Redis client for stream publishing
            ib_fetcher: IB historical data fetcher
            lookback_hours: Hours of historical data to fetch (24 = 1440 1m candles)
            ttl_seconds: TTL for warmup streams (auto-expire after consumption)
        """
        self.redis = redis_client
        self.ib_fetcher = ib_fetcher
        self.lookback_hours = lookback_hours
        self.ttl_seconds = ttl_seconds

    async def publish_warmup_data(self) -> bool:
        """Fetch and publish warmup data to Redis streams.

        Fetches historical 1m candles from IB Gateway for GC and DXY, publishes
        to warmup streams, and sets completion status flags.

        Returns:
            True if successful, False if IB Gateway unavailable

        Raises:
            Exception: Logs error but returns False instead of raising

        Side Effects:
            - Creates Redis streams: warmup.candles.1m.gc, warmup.candles.1m.dxy
            - Sets Redis hash: warmup:status
            - Sets TTL on all warmup keys
        """
        try:
            # Calculate time range (lookback_hours ago to now)
            end = datetime.now(UTC)
            start = end - timedelta(hours=self.lookback_hours)

            logger.info(
                f"Fetching warmup data from IB Gateway: "
                f"{start.isoformat()} to {end.isoformat()} "
                f"({self.lookback_hours} hours)"
            )

            # Fetch GC candles from IB Gateway
            logger.info("Fetching GC 1m candles...")
            gc_candles = await self.ib_fetcher.fetch_candles(
                symbol="GC",
                start=start,
                end=end,
                timeframe="1m",
            )

            if not gc_candles:
                logger.error("No GC candles fetched from IB Gateway")
                await self._set_error_status("No GC candles fetched")
                return False

            logger.info(f"Fetched {len(gc_candles)} GC candles")

            # Fetch DXY candles from IB Gateway (symbol mapped to DX for IB)
            logger.info("Fetching DXY 1m candles...")
            dxy_candles = await self.ib_fetcher.fetch_candles(
                symbol="DXY",  # IBHistoricalFetcher maps DXY -> DX
                start=start,
                end=end,
                timeframe="1m",
            )

            if not dxy_candles:
                logger.error("No DXY candles fetched from IB Gateway")
                await self._set_error_status("No DXY candles fetched")
                return False

            logger.info(f"Fetched {len(dxy_candles)} DXY candles")

            # Clear any existing warmup streams to avoid stale data mixing
            await self.redis.delete(
                "warmup.candles.1m.gc",
                "warmup.candles.1m.dxy",
            )

            # Publish GC candles to warmup stream
            logger.info("Publishing GC candles to warmup stream...")
            for candle in gc_candles:
                await self.redis.xadd(
                    "warmup.candles.1m.gc",
                    {"data": candle.model_dump_json()},
                )

            # Publish DXY candles to warmup stream
            logger.info("Publishing DXY candles to warmup stream...")
            for candle in dxy_candles:
                await self.redis.xadd(
                    "warmup.candles.1m.dxy",
                    {"data": candle.model_dump_json()},
                )

            # Set completion status in Redis hash
            await self.redis.hset(
                "warmup:status",
                mapping={
                    "gc": "complete",
                    "dxy": "complete",
                    "gc_count": str(len(gc_candles)),
                    "dxy_count": str(len(dxy_candles)),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

            # Set TTL on warmup streams (auto-expire)
            await self.redis.expire("warmup.candles.1m.gc", self.ttl_seconds)
            await self.redis.expire("warmup.candles.1m.dxy", self.ttl_seconds)
            await self.redis.expire("warmup:status", self.ttl_seconds)

            logger.info(
                f"Published warmup data: {len(gc_candles)} GC, "
                f"{len(dxy_candles)} DXY candles (TTL: {self.ttl_seconds}s)"
            )

            return True

        except Exception as e:
            logger.error(f"Error publishing warmup data: {e}", exc_info=True)
            await self._set_error_status(str(e))
            return False

    async def _set_error_status(self, error_message: str) -> None:
        """Set error status in Redis for downstream services.

        Deletes any existing warmup status hash to prevent stale success
        markers from previous runs from being visible to consumers.

        Args:
            error_message: Error message to log
        """
        try:
            # Delete entire status hash to clear any stale success markers
            # from previous warmup runs (prevents false positives within TTL)
            await self.redis.delete("warmup:status")

            # Set fresh error status
            await self.redis.hset(
                "warmup:status",
                mapping={
                    "error": error_message,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
            await self.redis.expire("warmup:status", self.ttl_seconds)
        except Exception as e:
            logger.error(f"Failed to set error status in Redis: {e}", exc_info=True)

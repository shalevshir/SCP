"""Warmup stream consumer utilities for service initialization.

This module provides utilities for consuming ephemeral warmup streams published
by the data-adapter service on startup. Services use these utilities to load
historical data without querying the database.
"""

import asyncio
import time
from datetime import datetime

import redis.asyncio as redis

from scp_shared.common.logger import get_logger
from scp_shared.messaging.schemas import CandleMessage

logger = get_logger(__name__)


async def check_warmup_available(redis_client: redis.Redis) -> dict:
    """Check if warmup streams exist and are complete.

    Args:
        redis_client: Redis client

    Returns:
        Dictionary with warmup availability status:
        {
            "available": bool,  # True if both streams exist and marked complete
            "gc_ready": bool,   # True if GC stream exists and marked complete
            "dxy_ready": bool,  # True if DXY stream exists and marked complete
            "gc_count": int,    # Number of GC candles (from status hash)
            "dxy_count": int,   # Number of DXY candles (from status hash)
        }
    """
    try:
        # Check for warmup status hash
        status = await redis_client.hgetall("warmup:status")

        if not status:
            logger.debug("Warmup status hash not found")
            return {
                "available": False,
                "gc_ready": False,
                "dxy_ready": False,
                "gc_count": 0,
                "dxy_count": 0,
            }

        # Decode bytes to strings
        status_decoded = {k.decode(): v.decode() for k, v in status.items()}

        gc_ready = status_decoded.get("gc") == "complete"
        dxy_ready = status_decoded.get("dxy") == "complete"
        gc_count = int(status_decoded.get("gc_count", 0))
        dxy_count = int(status_decoded.get("dxy_count", 0))

        available = gc_ready and dxy_ready

        logger.info(
            f"Warmup status: available={available}, "
            f"gc_ready={gc_ready} ({gc_count} candles), "
            f"dxy_ready={dxy_ready} ({dxy_count} candles)"
        )

        return {
            "available": available,
            "gc_ready": gc_ready,
            "dxy_ready": dxy_ready,
            "gc_count": gc_count,
            "dxy_count": dxy_count,
        }

    except Exception as e:
        logger.error(f"Error checking warmup availability: {e}", exc_info=True)
        return {
            "available": False,
            "gc_ready": False,
            "dxy_ready": False,
            "gc_count": 0,
            "dxy_count": 0,
        }


async def consume_warmup_stream(
    redis_client: redis.Redis,
    stream_name: str,
    timeout_seconds: int = 60,
) -> list[CandleMessage]:
    """Consume all candles from warmup stream.

    This function waits for the warmup stream to exist (polling with timeout),
    then reads all candles from the stream using XREAD.

    Args:
        redis_client: Redis client
        stream_name: Warmup stream name (e.g., "warmup.candles.1m.gc")
        timeout_seconds: Maximum time to wait for stream to exist

    Returns:
        List of CandleMessage objects sorted by timestamp ascending.
        Returns empty list if timeout or stream missing.

    Example:
        >>> gc_candles = await consume_warmup_stream(
        ...     redis_client,
        ...     "warmup.candles.1m.gc",
        ...     timeout_seconds=60
        ... )
        >>> len(gc_candles)
        1440  # 24 hours of 1m candles
    """
    start_time = time.time()

    # Wait for stream to exist (data-adapter may still be fetching from IB)
    logger.info(f"Waiting for warmup stream: {stream_name} (timeout: {timeout_seconds}s)")

    while time.time() - start_time < timeout_seconds:
        exists = await redis_client.exists(stream_name)
        if exists:
            logger.info(f"Warmup stream found: {stream_name}")
            break
        await asyncio.sleep(0.5)
    else:
        logger.warning(
            f"Warmup stream {stream_name} not found after {timeout_seconds}s timeout"
        )
        return []

    # Read entire stream from beginning (XREAD with "0-0" start ID)
    try:
        # Read in batches to avoid memory issues with large streams
        # XREAD returns: [(stream_name, [(entry_id, {field: value}), ...])]
        candles = []
        last_id = "0-0"
        batch_size = 1000

        while True:
            messages = await redis_client.xread(
                {stream_name: last_id},
                count=batch_size,
                block=1000,  # 1 second block timeout
            )

            if not messages:
                # No more messages
                break

            for stream, entries in messages:
                for entry_id, data in entries:
                    # Parse candle from JSON
                    candle_json = data.get(b"data")
                    if candle_json:
                        candle_json_str = candle_json.decode("utf-8")
                        candle = CandleMessage.model_validate_json(candle_json_str)
                        candles.append(candle)
                        last_id = entry_id.decode("utf-8")

            # If we got fewer than batch_size, we've reached the end
            if len(entries) < batch_size:
                break

        # Sort by timestamp (ascending order for replay)
        candles.sort(key=lambda c: c.timestamp)

        logger.info(
            f"Loaded {len(candles)} warmup candles from {stream_name} "
            f"(range: {candles[0].timestamp if candles else None} to "
            f"{candles[-1].timestamp if candles else None})"
        )

        return candles

    except Exception as e:
        logger.error(
            f"Error consuming warmup stream {stream_name}: {e}", exc_info=True
        )
        return []

#!/usr/bin/env python3
"""Replay historical data from Databento through the microservices pipeline.

This script fetches historical OHLCV data from Databento and replays it through
the data adapter service (via Redis) as if it were live data, allowing you to:

1. Test the live data integration with real historical data
2. Validate the full pipeline without a live connection
3. Replay specific date ranges at various speeds
4. Test with actual market conditions (gaps, volatility, etc.)

Usage:
    python scripts/replay_databento_historical.py \\
        --start 2024-11-05 \\
        --end 2024-11-12 \\
        --api-key db-your-key \\
        --speed 10.0

Requirements:
    - Databento API key with historical data access
    - Redis running (for publishing candles)
    - Optionally: all microservices running to see full pipeline
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import databento as db
import redis.asyncio as redis

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scp_shared.common import get_logger
from scp_shared.messaging import RedisStreamPublisher
from scp_shared.messaging.schemas import CandleMessage

logger = get_logger(__name__)


class DatabentoHistoricalReplay:
    """Replays historical OHLCV data from Databento through the pipeline."""
    
    def __init__(
        self,
        api_key: str,
        dataset: str = "GLBX.MDP3",
        gc_symbol: str = "GC.FUT",
        dxy_symbol: str = "DX.FUT",
    ):
        """Initialize Databento historical replay.
        
        Args:
            api_key: Databento API key
            dataset: Dataset identifier
            gc_symbol: Databento symbol for Gold
            dxy_symbol: Databento symbol for DXY
        """
        self.api_key = api_key
        self.dataset = dataset
        self.gc_symbol = gc_symbol
        self.dxy_symbol = dxy_symbol
        self.client = db.Historical(key=api_key)
    
    def _normalize_symbol(self, databento_symbol: str) -> str:
        """Normalize Databento symbol to internal format."""
        if "GC" in databento_symbol.upper():
            return "GC"
        elif "DX" in databento_symbol.upper():
            return "DXY"
        return databento_symbol
    
    def fetch_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> list[CandleMessage]:
        """Fetch historical OHLCV data from Databento.
        
        Args:
            symbol: Internal symbol (GC or DXY)
            start: Start datetime (UTC)
            end: End datetime (UTC)
            
        Returns:
            List of CandleMessage objects sorted by timestamp
        """
        # Map internal symbol to Databento symbol
        db_symbol = self.gc_symbol if symbol == "GC" else self.dxy_symbol
        
        logger.info(
            f"Fetching {symbol} data from Databento: "
            f"{start.isoformat()} to {end.isoformat()}"
        )
        
        try:
            # Fetch 1-minute OHLCV data
            data = self.client.timeseries.get_range(
                dataset=self.dataset,
                symbols=[db_symbol],
                schema="ohlcv-1m",
                start=start.isoformat(),
                end=end.isoformat(),
            )
            
            # Convert to CandleMessage objects
            candles = []
            for record in data:
                candle = CandleMessage(
                    timestamp=record.ts_event,
                    symbol=symbol,
                    timeframe="1m",
                    open=float(record.open) / 1e9,  # Databento fixed-point
                    high=float(record.high) / 1e9,
                    low=float(record.low) / 1e9,
                    close=float(record.close) / 1e9,
                    volume=float(record.volume),
                )
                candles.append(candle)
            
            logger.info(f"Fetched {len(candles)} candles for {symbol}")
            return candles
        
        except Exception as e:
            logger.error(f"Error fetching {symbol} data: {e}", exc_info=True)
            return []


async def replay_candles(
    candles_gc: list[CandleMessage],
    candles_dxy: list[CandleMessage],
    redis_url: str,
    speed_multiplier: float = 1.0,
    processing_delay: float = 5.0,
) -> dict:
    """Replay candles through Redis streams.
    
    Args:
        candles_gc: GC candles to replay
        candles_dxy: DXY candles to replay
        redis_url: Redis connection URL
        speed_multiplier: Replay speed (1.0 = real-time, 0 = turbo)
        processing_delay: Seconds to wait after replay for processing
        
    Returns:
        Statistics dictionary
    """
    # Connect to Redis
    redis_client = redis.Redis.from_url(redis_url)
    publisher = RedisStreamPublisher(redis_client)
    
    # Merge and sort all candles by timestamp
    all_candles = []
    for candle in candles_gc:
        all_candles.append(("GC", candle))
    for candle in candles_dxy:
        all_candles.append(("DXY", candle))
    
    all_candles.sort(key=lambda x: x[1].timestamp)
    
    logger.info(f"Replaying {len(all_candles)} total candles (speed: {speed_multiplier}x)")
    
    # Replay candles
    prev_timestamp = None
    published_count = 0
    
    for symbol, candle in all_candles:
        # Simulate time delay between candles
        if prev_timestamp is not None and speed_multiplier > 0:
            real_delay = (candle.timestamp - prev_timestamp).total_seconds()
            replay_delay = real_delay / speed_multiplier
            
            # Cap delay at 1 second for very slow replays
            if replay_delay > 1.0:
                replay_delay = 1.0
            
            if replay_delay > 0:
                await asyncio.sleep(replay_delay)
        
        # Publish to appropriate stream
        stream = f"candles.1m.{symbol.lower()}"
        await publisher.publish(stream, candle)
        published_count += 1
        
        # Log progress every 100 candles
        if published_count % 100 == 0:
            logger.info(f"Published {published_count}/{len(all_candles)} candles...")
        
        prev_timestamp = candle.timestamp
    
    logger.info(f"Replay complete: {published_count} candles published")
    
    # Wait for pipeline to process
    if processing_delay > 0:
        logger.info(f"Waiting {processing_delay}s for pipeline processing...")
        await asyncio.sleep(processing_delay)
    
    await redis_client.aclose()
    
    return {
        "success": True,
        "candles_published": published_count,
        "gc_candles": len(candles_gc),
        "dxy_candles": len(candles_dxy),
    }


async def main():
    """Main entry point for Databento historical replay."""
    parser = argparse.ArgumentParser(
        description="Replay historical data from Databento through the pipeline"
    )
    
    # Date range
    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date (YYYY-MM-DD or ISO 8601)",
    )
    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date (YYYY-MM-DD or ISO 8601)",
    )
    
    # Databento configuration
    parser.add_argument(
        "--api-key",
        type=str,
        required=True,
        help="Databento API key",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="GLBX.MDP3",
        help="Databento dataset (default: GLBX.MDP3)",
    )
    parser.add_argument(
        "--gc-symbol",
        type=str,
        default="GC.FUT",
        help="Databento symbol for Gold (default: GC.FUT)",
    )
    parser.add_argument(
        "--dxy-symbol",
        type=str,
        default="DX.FUT",
        help="Databento symbol for DXY (default: DX.FUT)",
    )
    
    # Redis configuration
    parser.add_argument(
        "--redis-url",
        type=str,
        default="redis://localhost:6379",
        help="Redis URL (default: redis://localhost:6379)",
    )
    
    # Replay configuration
    parser.add_argument(
        "--speed",
        type=float,
        default=10.0,
        help="Replay speed multiplier (1.0=realtime, 10.0=10x, 0=turbo) (default: 10.0)",
    )
    parser.add_argument(
        "--processing-delay",
        type=float,
        default=5.0,
        help="Seconds to wait after replay for processing (default: 5.0)",
    )
    
    args = parser.parse_args()
    
    # Parse dates
    try:
        if "T" in args.start:
            start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
        else:
            start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        
        if "T" in args.end:
            end = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
        else:
            end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            # Set to end of day
            end = end + timedelta(days=1) - timedelta(seconds=1)
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return 1
    
    logger.info("=" * 80)
    logger.info("Databento Historical Replay")
    logger.info("=" * 80)
    logger.info(f"Date range: {start.isoformat()} to {end.isoformat()}")
    logger.info(f"Dataset: {args.dataset}")
    logger.info(f"Symbols: {args.gc_symbol} (GC), {args.dxy_symbol} (DXY)")
    logger.info(f"Speed: {args.speed}x")
    logger.info(f"Redis: {args.redis_url}")
    logger.info("=" * 80)
    
    # Initialize Databento replay
    replay = DatabentoHistoricalReplay(
        api_key=args.api_key,
        dataset=args.dataset,
        gc_symbol=args.gc_symbol,
        dxy_symbol=args.dxy_symbol,
    )
    
    # Fetch historical data
    logger.info("Fetching historical data from Databento...")
    candles_gc = replay.fetch_historical_data("GC", start, end)
    candles_dxy = replay.fetch_historical_data("DXY", start, end)
    
    if not candles_gc:
        logger.error("No GC data fetched. Check your API key and date range.")
        return 1
    if not candles_dxy:
        logger.warning("No DXY data fetched. Continuing with GC only...")
    
    # Replay through pipeline
    logger.info("Starting replay...")
    stats = await replay_candles(
        candles_gc=candles_gc,
        candles_dxy=candles_dxy,
        redis_url=args.redis_url,
        speed_multiplier=args.speed,
        processing_delay=args.processing_delay,
    )
    
    # Print results
    logger.info("=" * 80)
    logger.info("Replay Complete")
    logger.info("=" * 80)
    logger.info(f"Total candles published: {stats['candles_published']}")
    logger.info(f"GC candles: {stats['gc_candles']}")
    logger.info(f"DXY candles: {stats['dxy_candles']}")
    logger.info("=" * 80)
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

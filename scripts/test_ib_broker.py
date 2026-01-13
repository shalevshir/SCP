#!/usr/bin/env python3
"""Test script to verify IB broker integration.

This script publishes valid signals and candles to Redis streams,
triggering the Execution service to place real orders via Interactive Brokers.

Usage:
    # Open a trade (long)
    poetry run python scripts/test_ib_broker.py open --direction long --price 2650.0

    # Open a trade (short)
    poetry run python scripts/test_ib_broker.py open --direction short --price 2650.0

    # Close all active trades
    poetry run python scripts/test_ib_broker.py close --price 2655.0

    # Check status
    poetry run python scripts/test_ib_broker.py status

Requirements:
    - Redis running (docker-compose up -d redis)
    - Execution service running with BROKER_MODE=ib_paper
    - IB Gateway/TWS running and connected
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import redis

# Default Redis URL
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Stream names (must match execution service)
STREAM_SIGNALS = "signals.pending"
STREAM_CANDLES = "candles.1m.gc"
STREAM_FEATURES = "features.1m"


def get_redis_client() -> redis.Redis:
    """Get Redis client."""
    return redis.Redis.from_url(REDIS_URL)


def create_signal_message(
    direction: str,
    entry_price: float,
    sl_offset: float = 6.0,
    tp_offset: float = 12.0,
) -> dict:
    """Create a valid signal message.
    
    Args:
        direction: "long" or "short"
        entry_price: Entry price
        sl_offset: Stop loss offset in points (default 6.0 = $600 risk)
        tp_offset: Take profit offset in points (default 12.0 = $1200 reward)
        
    Returns:
        Signal message dict
    """
    signal_id = str(uuid4())
    now = datetime.now(timezone.utc)
    
    if direction == "long":
        sl_price = entry_price - sl_offset
        tp_price = entry_price + tp_offset
    else:  # short
        sl_price = entry_price + sl_offset
        tp_price = entry_price - tp_offset
    
    return {
        "id": signal_id,
        "timestamp": now.isoformat(),
        "direction": direction,
        "setup_type": "VWAP_RECLAIM",
        "score": 9.0,
        "confidence": "A+",
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "factors": {
            "vwap_reclaim": True,
            "htf_bullish": direction == "long",
            "dxy_aligned": True,
            "test_signal": True,
        },
    }


def create_candle_message(
    timestamp: datetime,
    price: float,
    symbol: str = "GC",
) -> dict:
    """Create a valid candle message.
    
    Args:
        timestamp: Candle timestamp
        price: Base price (OHLC will be around this)
        symbol: Symbol (default "GC")
        
    Returns:
        Candle message dict
    """
    # Create realistic OHLC around the base price
    return {
        "timestamp": timestamp.isoformat(),
        "symbol": symbol,
        "timeframe": "1m",
        "open": price,
        "high": price + 0.5,
        "low": price - 0.5,
        "close": price + 0.2,
        "volume": 100.0,
    }


def create_features_message(
    timestamp: datetime,
    price: float,
    symbol: str = "GC",
) -> dict:
    """Create a valid features message.
    
    Args:
        timestamp: Features timestamp (must match candle)
        price: Base price
        symbol: Symbol (default "GC")
        
    Returns:
        Features message dict
    """
    return {
        "timestamp": timestamp.isoformat(),
        "symbol": symbol,
        "timeframe": "1m",
        "close": price + 0.2,
        "open": price,
        "high": price + 0.5,
        "low": price - 0.5,
        "volume": 100.0,
        "vwap": price,
        "vwap_slope": 0.1,
        "vwap_deviation": 0.5,
        "rsi": 55.0,
        "ema_9": price - 0.5,
        "ema_20": price - 1.0,
        "ema_50": price - 2.0,
        "dxy_correlation": -0.3,
        "dxy_corr": -0.3,
        "dxy_5m_corr": -0.25,
        "dxy_structure": "bearish",
        "structure_label": "HL",
        "htf_structure_label": "bullish",
        "bos_direction": "long",
        "bos_recent": True,
        "bos_age": 3,
        "choch_detected": False,
        "choch_direction": None,
        "structure_clarity": 0.8,
        "liquidity_sweep": False,
        "sweep_age": None,
        "expansion_detected": False,
        "expansion_reasons": [],
        "second_confirmation_long": True,
        "second_confirmation_short": False,
    }


def publish_to_stream(client: redis.Redis, stream: str, message: dict, message_type: str) -> str:
    """Publish message to Redis stream.
    
    Wraps message in the expected format (type, payload, published_at)
    to match RedisStreamPublisher format.
    
    Args:
        client: Redis client
        stream: Stream name
        message: Message dict
        message_type: Message class name (e.g., "SignalMessage")
        
    Returns:
        Message ID
    """
    # Wrap message in expected format (matching RedisStreamPublisher)
    data = {
        "type": message_type,
        "payload": json.dumps(message),
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    msg_id = client.xadd(stream, data)
    return msg_id.decode() if isinstance(msg_id, bytes) else msg_id


def open_trade(direction: str, price: float) -> None:
    """Open a trade by publishing signal and candles.
    
    The flow:
    1. Publish signal (T) - execution service buffers it
    2. Publish candle (T+1) - execution service executes signal at open
    
    Args:
        direction: "long" or "short"
        price: Entry price
    """
    client = get_redis_client()
    
    # Signal timestamp (T)
    signal_time = datetime.now(timezone.utc)
    
    # Execution candle timestamp (T+1)
    # The signal will execute at the OPEN of the next candle
    exec_time = signal_time + timedelta(minutes=1)
    
    print(f"\n{'='*60}")
    print(f"Opening {direction.upper()} trade @ {price:.2f}")
    print(f"{'='*60}")
    
    # 1. Publish signal
    signal = create_signal_message(direction, price)
    signal["timestamp"] = signal_time.isoformat()  # Override to signal time
    
    print(f"\n1. Publishing signal to {STREAM_SIGNALS}...")
    print(f"   Signal ID: {signal['id']}")
    print(f"   Direction: {signal['direction']}")
    print(f"   Entry: {signal['entry_price']:.2f}")
    print(f"   SL: {signal['sl_price']:.2f}")
    print(f"   TP: {signal['tp_price']:.2f}")
    
    msg_id = publish_to_stream(client, STREAM_SIGNALS, signal, "SignalMessage")
    print(f"   Published: {msg_id}")
    
    # 2. Wait a moment for signal to be processed
    print("\n2. Waiting 1s for signal processing...")
    import time
    time.sleep(1)
    
    # 3. Publish execution candle (T+1)
    # This triggers execute_pending_signals() with the candle's open price
    candle = create_candle_message(exec_time, price)
    
    print(f"\n3. Publishing execution candle to {STREAM_CANDLES}...")
    print(f"   Timestamp: {candle['timestamp']}")
    print(f"   Open: {candle['open']:.2f}")
    
    msg_id = publish_to_stream(client, STREAM_CANDLES, candle, "CandleMessage")
    print(f"   Published: {msg_id}")
    
    # 4. Publish matching features
    features = create_features_message(exec_time, price)
    
    print(f"\n4. Publishing features to {STREAM_FEATURES}...")
    msg_id = publish_to_stream(client, STREAM_FEATURES, features, "FeaturesMessage")
    print(f"   Published: {msg_id}")
    
    print(f"\n{'='*60}")
    print("✅ Messages published! Check execution service logs for trade entry.")
    print(f"{'='*60}\n")


def close_trade(price: float) -> None:
    """Close active trades by publishing candles that hit SL/TP.
    
    This is a simplified approach - it publishes candles with extreme
    high/low to trigger SL/TP exits.
    
    Args:
        price: Current market price
    """
    client = get_redis_client()
    now = datetime.now(timezone.utc)
    
    print(f"\n{'='*60}")
    print(f"Closing trades with candle @ {price:.2f}")
    print(f"{'='*60}")
    
    # Publish a candle with wide range to trigger SL/TP
    candle = create_candle_message(now, price)
    # Make the candle sweep a wide range to hit SL or TP
    candle["high"] = price + 20.0  # Will hit TP for longs
    candle["low"] = price - 20.0   # Will hit SL for longs / TP for shorts
    
    print(f"\n1. Publishing wide-range candle to {STREAM_CANDLES}...")
    print(f"   High: {candle['high']:.2f} (may hit TP)")
    print(f"   Low: {candle['low']:.2f} (may hit SL)")
    
    msg_id = publish_to_stream(client, STREAM_CANDLES, candle, "CandleMessage")
    print(f"   Published: {msg_id}")
    
    # Publish matching features
    features = create_features_message(now, price)
    
    print(f"\n2. Publishing features to {STREAM_FEATURES}...")
    msg_id = publish_to_stream(client, STREAM_FEATURES, features, "FeaturesMessage")
    print(f"   Published: {msg_id}")
    
    print(f"\n{'='*60}")
    print("✅ Wide-range candle published! Check logs for trade exits.")
    print(f"{'='*60}\n")


def check_status() -> None:
    """Check execution service status via health endpoint."""
    import urllib.request
    import urllib.error
    
    print(f"\n{'='*60}")
    print("Checking Execution Service Status")
    print(f"{'='*60}")
    
    try:
        # Health check
        with urllib.request.urlopen("http://localhost:8005/health", timeout=5) as resp:
            health = json.loads(resp.read().decode())
            print(f"\n✅ Service healthy: {health}")
    except urllib.error.URLError as e:
        print(f"\n❌ Service not reachable: {e}")
        return
    
    try:
        # Kill switch status
        with urllib.request.urlopen("http://localhost:8005/admin/status", timeout=5) as resp:
            status = json.loads(resp.read().decode())
            print(f"\n🔄 Kill switch status: {status}")
    except urllib.error.URLError as e:
        print(f"\n⚠️ Could not get kill switch status: {e}")
    
    # Check Redis streams
    client = get_redis_client()
    
    print("\n📊 Redis Stream Info:")
    for stream in [STREAM_SIGNALS, STREAM_CANDLES, STREAM_FEATURES]:
        try:
            info = client.xinfo_stream(stream)
            length = info.get(b"length", info.get("length", 0))
            print(f"   {stream}: {length} messages")
        except redis.ResponseError:
            print(f"   {stream}: (not created yet)")
    
    print(f"\n{'='*60}\n")


def reset_service() -> None:
    """Reset execution service state for testing."""
    import urllib.request
    import urllib.error
    
    print(f"\n{'='*60}")
    print("Resetting Execution Service State")
    print(f"{'='*60}")
    
    try:
        req = urllib.request.Request(
            "http://localhost:8005/admin/reset",
            method="POST",
            data=b"",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode())
            print(f"\n✅ Service reset: {result}")
    except urllib.error.URLError as e:
        print(f"\n❌ Could not reset service: {e}")
    
    print(f"\n{'='*60}\n")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test IB broker integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Open command
    open_parser = subparsers.add_parser("open", help="Open a test trade")
    open_parser.add_argument(
        "--direction", "-d",
        choices=["long", "short"],
        default="long",
        help="Trade direction (default: long)",
    )
    open_parser.add_argument(
        "--price", "-p",
        type=float,
        default=2650.0,
        help="Reference price for SL/TP calculation (default: 2650.0, actual entry is market)",
    )
    
    # Close command
    close_parser = subparsers.add_parser("close", help="Close active trades")
    close_parser.add_argument(
        "--price", "-p",
        type=float,
        default=2650.0,
        help="Reference price for close candle (default: 2650.0)",
    )
    
    # Status command
    subparsers.add_parser("status", help="Check service status")
    
    # Reset command
    subparsers.add_parser("reset", help="Reset service state")
    
    args = parser.parse_args()
    
    if args.command == "open":
        open_trade(args.direction, args.price)
    elif args.command == "close":
        close_trade(args.price)
    elif args.command == "status":
        check_status()
    elif args.command == "reset":
        reset_service()


if __name__ == "__main__":
    main()

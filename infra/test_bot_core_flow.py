#!/usr/bin/env python3
"""Test script to verify Bot Core signal flow."""

import asyncio
import json
from datetime import datetime, timezone

import redis.asyncio as redis


async def publish_test_messages():
    """Publish test HTF bias and features messages to verify signal generation."""
    client = redis.Redis.from_url("redis://localhost:6379")

    try:
        # 1. Publish HTF Bias
        bias_message = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": "GC",
            "timeframe": "1h",
            "bias": "bullish",
            "direction": "long",
            "score": 9.5,
            "confidence": "high",
            "structure_15m": "HH",
            "structure_1h": "HH",
            "dxy_aligned": True,
            "chop_detected": False,
        }

        bias_id = await client.xadd("htf.bias", bias_message)
        print(f"✓ Published HTF bias to htf.bias: {bias_id}")

        # Wait a moment for bias to be cached
        await asyncio.sleep(1)

        # 2. Publish Features (configured for A+ VWAP reclaim signal)
        features_message = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbol": "GC",
            "timeframe": "1m",
            "close": 2050.0,
            "vwap": 2048.0,  # Price above VWAP (bullish reclaim)
            "rsi": 55.0,  # Neutral RSI
            "ema_9": 2049.5,
            "ema_20": 2048.5,
            "ema_50": 2047.0,
            "dxy_correlation": -0.7,  # Strong negative correlation (good for gold)
            "structure_label": "HH",  # Higher high
            "vwap_deviation": 0.001,  # Small deviation (tight to VWAP)
        }

        features_id = await client.xadd("features.1m", features_message)
        print(f"✓ Published features to features.1m: {features_id}")

        # 3. Wait for processing
        print("⏳ Waiting 5 seconds for Bot Core to process...")
        await asyncio.sleep(5)

        # 4. Check for signals in signals.pending
        signals = await client.xread({"signals.pending": "0"}, count=10)

        if signals:
            print(f"\n✅ Found {len(signals[0][1])} signal(s) in signals.pending:")
            for stream_name, messages in signals:
                for msg_id, msg_data in messages:
                    print(f"  Signal ID: {msg_id}")
                    print(f"  Direction: {msg_data.get(b'direction', b'N/A').decode()}")
                    print(f"  Setup: {msg_data.get(b'setup_type', b'N/A').decode()}")
                    print(f"  Score: {msg_data.get(b'score', b'N/A').decode()}")
                    print(
                        f"  Confidence: {msg_data.get(b'confidence', b'N/A').decode()}"
                    )
                    print()
        else:
            print("\n⚠️  No signals found in signals.pending")
            print("   This may indicate:")
            print("   - Bot Core guardrails blocked the signal")
            print("   - Session validation failed")
            print("   - Signal score was below A+ threshold")

        # 5. Check stream info
        try:
            stream_info = await client.xinfo_stream("signals.pending")
            print(f"\nsignals.pending stream info:")
            print(f"  Length: {stream_info.get(b'length', 0)}")
            print(f"  Groups: {stream_info.get(b'groups', 0)}")
        except:
            print("\nsignals.pending stream does not exist yet")

    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(publish_test_messages())

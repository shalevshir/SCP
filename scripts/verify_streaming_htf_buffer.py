#!/usr/bin/env python3
"""Quick verification that StreamingFeatureProcessor is using correct buffer sizes."""

import logging

from feature_engine.streaming import StreamingFeatureProcessor

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s - %(message)s")


def main():
    print("=" * 60)
    print("Verifying StreamingFeatureProcessor Buffer Sizes")
    print("=" * 60)

    # Create processors for different timeframes
    timeframes = ["1m", "5m", "15m", "1h"]

    for tf in timeframes:
        print(f"\nCreating processor for {tf}...")
        processor = StreamingFeatureProcessor(timeframe=tf, swing_window=3)

        actual_size = processor.structure_buffer.maxlen
        print(f"  ✓ Structure buffer size: {actual_size} bars")

        # Verify expected sizes
        expected_sizes = {"1m": 30, "5m": 40, "15m": 50, "1h": 100}

        expected = expected_sizes.get(tf, 30)
        if actual_size == expected:
            print(f"  ✓ Matches expected size ({expected})")
        else:
            print(f"  ✗ ERROR: Expected {expected}, got {actual_size}")

    print("\n" + "=" * 60)
    print("Verification complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()





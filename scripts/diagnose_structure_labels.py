#!/usr/bin/env python3
"""Diagnose why structure labels aren't reaching the calculator."""

import logging
from datetime import UTC

import pandas as pd
from common.types import Candle
from feature_engine.streaming import StreamingFeatureProcessor

# Enable DEBUG logging
logging.basicConfig(
    level=logging.DEBUG, format="%(name)s - %(levelname)s - %(message)s"
)


def main():
    print("=" * 70)
    print("Diagnosing Structure Label Flow")
    print("=" * 70)

    # Create 1H processor with ACTUAL swing_window used in backtests (5, not 3!)
    # StreamingHTFFeatureComputer in features.py uses swing_window=5 by default
    processor = StreamingFeatureProcessor(timeframe="1h", swing_window=5)

    print(f"\nBuffer size: {processor.structure_buffer.maxlen}")
    print(f"Required bars for structure: {3 * processor.swing_window + 1}")

    # Create sample data with clear swings
    # This simulates ~100 hours of 1H data with clear HH/HL pattern
    print("\nFeeding 100 bars of 1H data with clear uptrend pattern...")

    base_price = 2000.0

    for i in range(100):
        # Create uptrend with swings
        trend_component = i * 2  # Overall uptrend
        swing = 10 * (1 if (i // 5) % 2 == 0 else -1)  # Oscillate every 5 bars

        open_price = base_price + trend_component + swing
        high = open_price + 8
        low = open_price - 5
        close = open_price + 3

        timestamp = pd.Timestamp(f"2025-01-01 {i:02d}:00:00", tz=UTC)
        if i >= 24:
            day = i // 24 + 1
            hour = i % 24
            timestamp = pd.Timestamp(f"2025-01-{day:02d} {hour:02d}:00:00", tz=UTC)

        gc_bar = Candle(
            timestamp=timestamp,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=1000.0,
            symbol="GC",
            timeframe="1h",
            source="TEST",
        )

        dxy_bar = Candle(
            timestamp=timestamp,
            open=100.0,
            high=100.5,
            low=99.5,
            close=100.0,
            volume=1000.0,
            symbol="DXY",
            timeframe="1h",
            source="TEST",
        )

        features = processor.update(gc_bar, dxy_bar)

        # Check structure label
        structure_label = features.get("structure_label")

        if i % 10 == 0 or structure_label not in (None, ""):
            print(f"\nBar {i}: timestamp={timestamp}")
            print(f"  Buffer size: {len(processor.structure_buffer)}")
            print(
                f"  structure_label: {structure_label!r} (type: {type(structure_label).__name__})"
            )
            print(f"  last_structure_label: {processor.last_structure_label!r}")

            if structure_label and structure_label in ("HH", "HL", "LH", "LL"):
                print("  ✅ VALID STRUCTURE LABEL DETECTED!")

    print("\n" + "=" * 70)
    print("Final State:")
    print(f"  last_structure_label: {processor.last_structure_label!r}")
    print(f"  Buffer size: {len(processor.structure_buffer)}")
    print("=" * 70)


if __name__ == "__main__":
    main()

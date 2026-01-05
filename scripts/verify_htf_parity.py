#!/usr/bin/env python3
"""Verify HTF logic parity between microservices and legacy implementations.

This script feeds identical data to both HTF implementations and compares:
1. HTF bias calculations (bias, direction, score, confidence)
2. Structure detection (1H and 15M labels)
3. Candle aggregation (1M → 15M → 1H)

Usage:
    poetry run python scripts/verify_htf_parity.py --data data/gc_1m_2024_jan.csv
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

# Import both implementations
from common.types import Candle as LegacyCandle
from rule_engine.htf.streaming import StreamingHTFBiasCalculator as LegacyHTFCalc

from scp_shared.common.types import Candle as MicroCandle
from scp_shared.rule_engine.htf.streaming import (
    StreamingHTFBiasCalculator as MicroHTFCalc,
)


def load_data(csv_path: Path) -> pd.DataFrame:
    """Load 1M candle data from CSV."""
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def create_candle(row: pd.Series, candle_class) -> Candle:
    """Create Candle object from DataFrame row."""
    return candle_class(
        timestamp=row["timestamp"].to_pydatetime(),
        symbol=row.get("symbol", "GC"),
        timeframe="1m",
        source="csv",
        open=row["open"],
        high=row["high"],
        low=row["low"],
        close=row["close"],
        volume=row.get("volume", 0),
    )


def compare_htf_bias(micro_bias, legacy_bias) -> dict:
    """Compare two HTFBias objects and return differences."""
    if micro_bias is None and legacy_bias is None:
        return {"match": True, "reason": "Both None"}
    
    if micro_bias is None or legacy_bias is None:
        return {
            "match": False,
            "reason": f"One is None (micro={micro_bias is not None}, legacy={legacy_bias is not None})",
        }
    
    differences = []
    
    # Compare bias
    if micro_bias.bias != legacy_bias.bias:
        differences.append(
            f"bias: micro={micro_bias.bias}, legacy={legacy_bias.bias}"
        )
    
    # Compare direction
    if micro_bias.direction != legacy_bias.direction:
        differences.append(
            f"direction: micro={micro_bias.direction}, legacy={legacy_bias.direction}"
        )
    
    # Compare score (within 0.1 tolerance)
    score_diff = abs(micro_bias.score - legacy_bias.score)
    if score_diff > 0.1:
        differences.append(
            f"score: micro={micro_bias.score:.2f}, legacy={legacy_bias.score:.2f} (diff={score_diff:.2f})"
        )
    
    # Compare confidence
    if micro_bias.confidence != legacy_bias.confidence:
        differences.append(
            f"confidence: micro={micro_bias.confidence}, legacy={legacy_bias.confidence}"
        )
    
    # Compare structure labels
    if micro_bias.structure_1h != legacy_bias.structure_1h:
        differences.append(
            f"structure_1h: micro={micro_bias.structure_1h}, legacy={legacy_bias.structure_1h}"
        )
    
    if micro_bias.structure_15m != legacy_bias.structure_15m:
        differences.append(
            f"structure_15m: micro={micro_bias.structure_15m}, legacy={legacy_bias.structure_15m}"
        )
    
    return {
        "match": len(differences) == 0,
        "differences": differences if differences else None,
        "score_diff": score_diff if 'score_diff' in locals() else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description="Verify HTF logic parity")
    parser.add_argument(
        "--data",
        type=Path,
        required=True,
        help="Path to 1M candle CSV (GC)",
    )
    parser.add_argument(
        "--dxy-data",
        type=Path,
        help="Path to 1M DXY candle CSV (optional)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/htf_parity_report.json"),
        help="Output report path",
    )
    parser.add_argument(
        "--max-bars",
        type=int,
        default=None,
        help="Limit number of bars to process (for testing)",
    )
    args = parser.parse_args()
    
    print("=" * 80)
    print("HTF LOGIC PARITY VERIFICATION")
    print("=" * 80)
    print(f"Data source: {args.data}")
    print(f"Output: {args.output}")
    print()
    
    # Load data
    print("Loading data...")
    gc_df = load_data(args.data)
    
    # For now, use GC data as DXY proxy (TODO: load separate DXY data)
    dxy_df = load_data(args.dxy_data) if args.dxy_data else gc_df.copy()
    
    if args.max_bars:
        gc_df = gc_df.head(args.max_bars)
        dxy_df = dxy_df.head(args.max_bars)
    
    print(f"Loaded {len(gc_df)} 1M bars")
    print()
    
    # Initialize both calculators
    print("Initializing HTF calculators...")
    micro_calc = MicroHTFCalc()
    legacy_calc = LegacyHTFCalc()
    print()
    
    # Process bars and compare
    print("Processing bars...")
    results = []
    mismatches = []
    matches = 0
    total_bias_updates = 0
    
    for idx, (gc_row, dxy_row) in enumerate(zip(gc_df.itertuples(), dxy_df.itertuples())):
        # Create candles for both implementations
        gc_micro = create_candle(gc_row, MicroCandle)
        dxy_micro = create_candle(dxy_row, MicroCandle)
        
        gc_legacy = create_candle(gc_row, LegacyCandle)
        dxy_legacy = create_candle(dxy_row, LegacyCandle)
        
        # Update both calculators
        micro_bias = micro_calc.update(gc_micro, dxy_micro)
        legacy_bias = legacy_calc.update(gc_legacy, dxy_legacy)
        
        # Compare if both produced bias updates
        if micro_bias is not None or legacy_bias is not None:
            total_bias_updates += 1
            comparison = compare_htf_bias(micro_bias, legacy_bias)
            
            result = {
                "bar_idx": idx,
                "timestamp": str(gc_row.timestamp),
                "comparison": comparison,
                "micro_bias": {
                    "bias": micro_bias.bias if micro_bias else None,
                    "direction": micro_bias.direction if micro_bias else None,
                    "score": micro_bias.score if micro_bias else None,
                    "structure_1h": micro_bias.structure_1h if micro_bias else None,
                    "structure_15m": micro_bias.structure_15m if micro_bias else None,
                } if micro_bias else None,
                "legacy_bias": {
                    "bias": legacy_bias.bias if legacy_bias else None,
                    "direction": legacy_bias.direction if legacy_bias else None,
                    "score": legacy_bias.score if legacy_bias else None,
                    "structure_1h": legacy_bias.structure_1h if legacy_bias else None,
                    "structure_15m": legacy_bias.structure_15m if legacy_bias else None,
                } if legacy_bias else None,
            }
            results.append(result)
            
            if comparison["match"]:
                matches += 1
            else:
                mismatches.append(result)
                print(f"❌ Mismatch at bar {idx} ({gc_row.timestamp}):")
                for diff in comparison.get("differences", []):
                    print(f"   - {diff}")
        
        # Progress indicator
        if (idx + 1) % 1000 == 0:
            print(f"   Processed {idx + 1} bars...")
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total bars processed: {len(gc_df)}")
    print(f"HTF bias updates: {total_bias_updates}")
    print(f"Matches: {matches} ({matches/total_bias_updates*100:.1f}%)")
    print(f"Mismatches: {len(mismatches)} ({len(mismatches)/total_bias_updates*100:.1f}%)")
    print()
    
    if len(mismatches) > 0:
        print("⚠️ PARITY ISSUE DETECTED")
        print(f"Found {len(mismatches)} mismatches between implementations")
        print()
        print("Top 5 mismatches:")
        for result in mismatches[:5]:
            print(f"  Bar {result['bar_idx']} at {result['timestamp']}:")
            for diff in result['comparison'].get('differences', []):
                print(f"    - {diff}")
        print()
        print(f"Full report saved to: {args.output}")
    else:
        print("✅ PARITY VERIFIED")
        print("Both implementations produce identical results!")
    
    # Save detailed report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "summary": {
            "total_bars": len(gc_df),
            "bias_updates": total_bias_updates,
            "matches": matches,
            "mismatches": len(mismatches),
            "match_rate": matches / total_bias_updates if total_bias_updates > 0 else 0.0,
        },
        "mismatches": mismatches,
        "metadata": {
            "data_source": str(args.data),
            "timestamp": datetime.now().isoformat(),
        },
    }
    
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    
    print()
    print(f"Detailed report saved to: {args.output}")
    
    # Exit with error code if mismatches found
    return 1 if len(mismatches) > 0 else 0


if __name__ == "__main__":
    exit(main())



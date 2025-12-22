#!/usr/bin/env python3
"""
Trace where signals are being rejected in the pipeline.

This script instruments the replay loop to count:
1. How many candles are processed
2. How many trigger VWAP/structure conditions
3. How many pass initial scoring
4. How many pass validation
5. How many get executed
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from datetime import datetime, timedelta
from backtester.replay_loop import replay_backtest
from config.config_loader import load_config


def trace_pipeline_with_logging(
    data_dir: str, start_date: str, end_date: str, warmup_days: int = 2
):
    """Run backtest with detailed logging to trace signal rejection."""

    print("🔍 Tracing Signal Rejection Pipeline")
    print("=" * 80)

    # Load config
    config = load_config()

    # Parse dates
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    # Add warmup
    warmup_start = start_dt - timedelta(days=warmup_days)

    print(f"\n📅 Date Range:")
    print(f"   Warmup: {warmup_start.date()} to {start_dt.date()}")
    print(f"   Backtest: {start_dt.date()} to {end_dt.date()}")

    # Load data
    print(f"\n📂 Loading data from {data_dir}...")
    gc_files = sorted(Path(data_dir).glob("gc/*.parquet"))
    dxy_files = sorted(Path(data_dir).glob("dx/*.parquet"))

    if not gc_files or not dxy_files:
        print("❌ Data files not found!")
        return

    # Load GC data
    gc_dfs = []
    for file in gc_files:
        df = pd.read_parquet(file)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        gc_dfs.append(df)

    gc_df = pd.concat(gc_dfs, ignore_index=True)
    gc_df = gc_df.sort_values("timestamp").reset_index(drop=True)

    # Filter to warmup + backtest period
    gc_df = gc_df[
        (gc_df["timestamp"] >= warmup_start)
        & (gc_df["timestamp"] <= end_dt + timedelta(days=1))
    ]

    # Load DXY data
    dxy_dfs = []
    for file in dxy_files:
        df = pd.read_parquet(file)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        dxy_dfs.append(df)

    dxy_df = pd.concat(dxy_dfs, ignore_index=True)
    dxy_df = dxy_df.sort_values("timestamp").reset_index(drop=True)
    dxy_df = dxy_df[
        (dxy_df["timestamp"] >= warmup_start)
        & (dxy_df["timestamp"] <= end_dt + timedelta(days=1))
    ]

    print(f"\n📊 Data Loaded:")
    print(f"   GC candles: {len(gc_df)}")
    print(f"   DXY candles: {len(dxy_df)}")

    # Count unique days
    unique_days = gc_df["timestamp"].dt.date.nunique()
    print(f"   Unique days: {unique_days}")
    print(f"   Avg candles/day: {len(gc_df) / unique_days:.0f}")

    # Now let's check what percentage have necessary data
    print(f"\n🔍 Checking Data Quality:")

    # Check for required columns
    required_gc_cols = ["open", "high", "low", "close", "volume"]
    missing_cols = [col for col in required_gc_cols if col not in gc_df.columns]

    if missing_cols:
        print(f"   ❌ Missing columns in GC data: {missing_cols}")
    else:
        print(f"   ✅ All required GC columns present")

    # Check for NaN values
    nan_counts = gc_df[required_gc_cols].isna().sum()
    if nan_counts.sum() > 0:
        print(f"   ⚠️  NaN values found:")
        for col, count in nan_counts.items():
            if count > 0:
                print(f"      {col}: {count} ({count/len(gc_df)*100:.1f}%)")
    else:
        print(f"   ✅ No NaN values in OHLCV data")

    # Run actual backtest
    print(f"\n🚀 Running backtest with instrumentation...")
    print(f"   (Check logs for signal rejection details)")

    results = replay_backtest(
        gc_df=gc_df,
        dxy_df=dxy_df,
        config=config,
        start_date=start_date,
        end_date=end_date,
        enable_console_logs=True,  # Enable detailed logging
        start_time=None,
        speed=None,
    )

    print(f"\n📊 Backtest Results:")
    print(f"   Total trades: {len(results.trades)}")
    print(f"   Win rate: {results.metrics.win_rate:.1f}%")
    print(f"   Total PnL: ${results.metrics.total_pnl_dollars:.2f}")

    return results


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: python trace_signal_rejection.py <data_dir> <start_date> <end_date> [warmup_days]"
        )
        sys.exit(1)

    data_dir = sys.argv[1]
    start_date = sys.argv[2]
    end_date = sys.argv[3]
    warmup_days = int(sys.argv[4]) if len(sys.argv) > 4 else 2

    trace_pipeline_with_logging(data_dir, start_date, end_date, warmup_days)






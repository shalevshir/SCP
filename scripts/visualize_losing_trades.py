"""Visualize losing trades with entry/exit points.

Generates charts showing price action around each losing trade with:
- Entry point (green arrow)
- Exit point / SL hit (red arrow)
- VWAP line
- Stop loss and take profit levels

Usage:
    python scripts/visualize_losing_trades.py --report reports/backtest_20260204_140127.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def load_ohlcv_data(symbol: str, timeframe: str = "1m") -> pd.DataFrame:
    """Load OHLCV data from CSV."""
    data_path = PROJECT_ROOT / "data" / "gc_dx_ohlcv" / f"{symbol}_ohlcv-{timeframe}.csv"
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    df = pd.read_csv(data_path)

    # Parse timestamp
    if "ts_event" in df.columns:
        df["timestamp"] = pd.to_datetime(df["ts_event"])
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    else:
        raise ValueError(f"No timestamp column found in {data_path}")

    df = df.set_index("timestamp").sort_index()
    return df


def load_backtest_report(report_path: str) -> dict:
    """Load backtest report JSON."""
    with open(report_path) as f:
        return json.load(f)


def get_losing_trades(report: dict) -> list[dict]:
    """Extract trades that hit SL."""
    trades = report.get("trades", [])
    losing = []
    for t in trades:
        exit_reason = t.get("exit_reason", "")
        if "SL_HIT" in exit_reason or "SL" in exit_reason:
            losing.append(t)
    return losing


def plot_trade(trade: dict, ohlcv: pd.DataFrame, output_dir: Path) -> str:
    """Plot a single trade with price action context."""
    entry_time = pd.to_datetime(trade["timestamp"])
    exit_time = pd.to_datetime(trade["exit_timestamp"]) if trade.get("exit_timestamp") else entry_time + timedelta(minutes=30)

    entry_price = trade["entry_price"]
    sl_price = trade["stop_loss"]
    tp_price = trade.get("take_profit_1", trade.get("take_profit"))
    exit_price = trade.get("exit_price", sl_price)
    direction = trade["direction"]
    setup_type = trade["setup_type"]

    # Get window of data (30 mins before entry to 15 mins after exit)
    window_start = entry_time - timedelta(minutes=30)
    window_end = exit_time + timedelta(minutes=15)

    # Filter data to window
    mask = (ohlcv.index >= window_start) & (ohlcv.index <= window_end)
    df_window = ohlcv[mask].copy()

    if len(df_window) < 5:
        print(f"  Warning: Not enough data points for trade at {entry_time}")
        return ""

    # Create figure with candlestick-like visualization
    fig, ax = plt.subplots(figsize=(14, 8))

    # Plot candlesticks
    for idx, row in df_window.iterrows():
        color = "green" if row["close"] >= row["open"] else "red"
        # Wick
        ax.plot([idx, idx], [row["low"], row["high"]], color="black", linewidth=0.5)
        # Body
        body_bottom = min(row["open"], row["close"])
        body_height = abs(row["close"] - row["open"])
        if body_height < 0.1:
            body_height = 0.1  # Minimum visible body
        rect = plt.Rectangle(
            (mdates.date2num(idx) - 0.0003, body_bottom),
            0.0006,
            body_height,
            facecolor=color,
            edgecolor="black",
            linewidth=0.5
        )
        ax.add_patch(rect)

    # Plot high/low as simple line chart for better visibility
    ax.plot(df_window.index, df_window["high"], color="gray", alpha=0.3, linewidth=0.5)
    ax.plot(df_window.index, df_window["low"], color="gray", alpha=0.3, linewidth=0.5)
    ax.fill_between(df_window.index, df_window["low"], df_window["high"], alpha=0.1, color="blue")

    # Plot close price as main line
    ax.plot(df_window.index, df_window["close"], color="blue", linewidth=1, alpha=0.7, label="Close")

    # Plot entry point
    ax.axhline(y=entry_price, color="blue", linestyle="--", linewidth=1.5, label=f"Entry: {entry_price:.1f}")
    ax.scatter([entry_time], [entry_price], color="blue", marker="^" if direction == "long" else "v", s=200, zorder=5, edgecolor="black", linewidth=1)

    # Plot SL level
    ax.axhline(y=sl_price, color="red", linestyle="-", linewidth=2, label=f"SL: {sl_price:.1f}")

    # Plot TP level
    if tp_price:
        ax.axhline(y=tp_price, color="green", linestyle="-", linewidth=1, alpha=0.7, label=f"TP: {tp_price:.1f}")

    # Plot exit point
    ax.scatter([exit_time], [exit_price], color="red", marker="x", s=200, zorder=5, linewidth=3)

    # Mark entry and exit times with vertical lines
    ax.axvline(x=entry_time, color="blue", linestyle=":", alpha=0.5)
    ax.axvline(x=exit_time, color="red", linestyle=":", alpha=0.5)

    # Formatting
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=5))
    plt.xticks(rotation=45)

    # Title and labels
    duration = trade.get("duration_minutes", "?")
    pnl_r = trade.get("pnl_r", "?")
    title = f"{setup_type} {direction.upper()} | Entry: {entry_time.strftime('%Y-%m-%d %H:%M')} | Duration: {duration} mins | PnL: {pnl_r}R"
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("Price")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)

    # Add annotations
    ax.annotate(
        f"ENTRY\n{entry_price:.1f}",
        xy=(entry_time, entry_price),
        xytext=(10, 30 if direction == "short" else -30),
        textcoords="offset points",
        fontsize=9,
        color="blue",
        ha="left"
    )
    ax.annotate(
        f"EXIT (SL)\n{exit_price:.1f}",
        xy=(exit_time, exit_price),
        xytext=(10, -30 if direction == "long" else 30),
        textcoords="offset points",
        fontsize=9,
        color="red",
        ha="left"
    )

    plt.tight_layout()

    # Save
    filename = f"trade_{entry_time.strftime('%Y%m%d_%H%M')}_{setup_type}_{direction}_SL.png"
    output_path = output_dir / filename
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    return str(output_path)


def main():
    parser = argparse.ArgumentParser(description="Visualize losing trades")
    parser.add_argument("--report", required=True, help="Path to backtest report JSON")
    parser.add_argument("--output", default="reports/trade_charts", help="Output directory for charts")
    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load report and data
    print(f"Loading backtest report: {args.report}")
    report = load_backtest_report(args.report)

    print("Loading OHLCV data...")
    ohlcv = load_ohlcv_data("GC", "1m")
    print(f"  Loaded {len(ohlcv)} candles from {ohlcv.index.min()} to {ohlcv.index.max()}")

    # Get losing trades
    losing_trades = get_losing_trades(report)
    print(f"\nFound {len(losing_trades)} losing trades (SL hit)")

    # Generate charts
    generated = []
    for i, trade in enumerate(losing_trades, 1):
        print(f"\n[{i}/{len(losing_trades)}] Plotting trade at {trade['timestamp']}...")
        try:
            path = plot_trade(trade, ohlcv, output_dir)
            if path:
                generated.append(path)
                print(f"  Saved: {path}")
        except Exception as e:
            print(f"  Error: {e}")

    print(f"\n{'='*60}")
    print(f"Generated {len(generated)} charts in {output_dir}/")
    for path in generated:
        print(f"  - {Path(path).name}")


if __name__ == "__main__":
    main()

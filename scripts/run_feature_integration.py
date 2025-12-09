#!/usr/bin/env python3
"""Run FeatureEngine integration against local CSV data.

This helper script loads GC and DXY candles via HistoricalDataLoader and runs
the FeatureEngine integration layer to produce a feature DataFrame. It prints a
summary to stdout and can optionally write the full dataset to CSV.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from data_layer.loader import HistoricalDataLoader
from feature_engine import process_features


def parse_iso_datetime(value: str) -> datetime:
    """Parse ISO-8601 datetime strings, defaulting to UTC when tzinfo missing."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run FeatureEngine integration using CSV data."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/gc_dx_ohlcv"),
        help="Directory containing GC/DX CSV files (default: data/gc_dx_ohlcv).",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="1m",
        choices=["1s", "1m", "15m", "1h"],
        help="Timeframe to load (default: 1m).",
    )
    parser.add_argument(
        "--start",
        type=parse_iso_datetime,
        default=datetime(2025, 1, 1, 9, 0, tzinfo=UTC),
        help="Start datetime (ISO-8601, default: 2025-01-01T09:00:00+00:00).",
    )
    parser.add_argument(
        "--end",
        type=parse_iso_datetime,
        default=datetime(2025, 1, 1, 13, 0, tzinfo=UTC),
        help="End datetime (ISO-8601, default: 2025-01-01T13:00:00+00:00).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path to write the resulting feature DataFrame as CSV.",
    )
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    loader = HistoricalDataLoader(args.data_dir)
    symbols = ["GC", "DXY"]
    data = loader.load(symbols, args.timeframe, args.start, args.end)

    missing_symbols = [symbol for symbol in symbols if symbol not in data]
    if missing_symbols:
        raise RuntimeError(f"Missing data for symbols: {missing_symbols}")

    features = process_features(
        gc_df=data["GC"], dxy_df=data["DXY"], timeframe=args.timeframe
    )

    print("=== FeatureEngine Integration Summary ===")
    print(f"Rows: {len(features)}")
    print(f"Columns: {list(features.columns)}")
    print("Head:")
    print(features.head())
    print("\nTail:")
    print(features.tail())

    if args.output:
        features.to_csv(args.output, index=False)
        print(f"\nSaved feature DataFrame to: {args.output}")


if __name__ == "__main__":
    main()

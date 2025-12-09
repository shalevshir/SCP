"""
CSV data cleaning script for Shir Capital trading data.

This script processes raw OHLCV CSV files to:
1. Remove spread instruments (e.g., "GC-DX", "GCZ24-GCF25")
2. Filter only instruments starting with specified prefix (GC or DX)
3. Select the contract with highest volume at each minute (skipping rows with invalid OHLC)
4. Remove duplicate timestamps
5. Sort by timestamp

Note: Zero or negative OHLC values indicate data errors and are automatically skipped.
The script selects the highest volume contract with valid (positive) OHLC values.

Usage:
    python scripts/clean_csv_data.py --input data/gc_dx_ohlcv/glbx_ohlcv_1m.csv --output data/gc_dx_ohlcv/GC_ohlcv_1m.csv --prefix GC
    python scripts/clean_csv_data.py --input data/gc_dx_ohlcv/dxy_ohlcv_1m.csv.csv --output data/gc_dx_ohlcv/DX_ohlcv_1m.csv --prefix DX
"""

import argparse
import logging
from pathlib import Path
from typing import Literal

import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def is_spread_instrument(symbol: str) -> bool:
    """
    Check if a symbol represents a spread instrument.

    Spread instruments contain dashes indicating a relationship between
    two or more instruments (e.g., "GC-DX", "GCZ24-GCF25").

    Args:
        symbol: Instrument symbol to check

    Returns:
        True if the symbol is a spread instrument, False otherwise
    """
    return "-" in symbol


def filter_primary_instruments(
    df: pd.DataFrame,
    prefix: Literal["GC", "DX"],
) -> pd.DataFrame:
    """
    Filter dataframe to keep only primary instruments with specified prefix.

    Removes:
    - Spread instruments (containing dashes)
    - Instruments not starting with the specified prefix

    Args:
        df: DataFrame with 'symbol' column
        prefix: Instrument prefix to filter for ("GC" or "DX")

    Returns:
        Filtered DataFrame containing only primary instruments with specified prefix
    """
    # Remove spread instruments
    mask_not_spread = ~df["symbol"].apply(is_spread_instrument)

    # Keep only instruments starting with prefix (case-insensitive)
    mask_prefix = df["symbol"].str.upper().str.startswith(prefix.upper())

    # Combine filters
    filtered_df = df[mask_not_spread & mask_prefix].copy()

    logger.info(
        f"Filtered from {len(df)} to {len(filtered_df)} rows "
        f"(removed spreads and non-{prefix} instruments)"
    )

    return filtered_df


def select_highest_volume_per_minute(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each unique timestamp, keep only the row with highest volume.

    When multiple contracts exist at the same timestamp (e.g., GCZ24, GCF25),
    this selects the contract with highest trading volume, which is typically
    the most liquid and relevant for trading.

    If the highest volume row has zero or negative OHLC values (data error),
    it skips to the next highest volume row with valid data.

    Args:
        df: DataFrame with 'ts_event' and 'volume' columns

    Returns:
        DataFrame with one row per unique timestamp (highest volume row with valid OHLC)
    """
    if df.empty:
        return df

    # Sort by timestamp and volume (descending) to process highest volume first
    df_sorted = df.sort_values(["ts_event", "volume"], ascending=[True, False]).copy()

    # Filter out rows with zero or negative OHLC values (data errors)
    valid_mask = (
        (df_sorted["open"] > 0)
        & (df_sorted["high"] > 0)
        & (df_sorted["low"] > 0)
        & (df_sorted["close"] > 0)
    )

    invalid_count = (~valid_mask).sum()
    if invalid_count > 0:
        logger.warning(
            f"Found {invalid_count} rows with zero or negative OHLC values - skipping these rows"
        )

    df_valid = df_sorted[valid_mask].copy()

    if df_valid.empty:
        logger.warning(
            "No valid rows remaining after filtering zero/negative OHLC values"
        )
        return df_valid

    # Group by timestamp and select first row (highest volume with valid data)
    result_df = df_valid.groupby("ts_event", as_index=False).first()

    original_minutes = df["ts_event"].nunique()
    result_minutes = result_df["ts_event"].nunique()

    logger.info(
        f"Selected highest volume contracts: {len(df)} rows -> {len(result_df)} rows "
        f"({result_minutes} unique minutes)"
    )

    if original_minutes != result_minutes:
        logger.warning(
            f"Timestamp count mismatch: {original_minutes} unique timestamps in input, "
            f"{result_minutes} in output (may be due to all rows having invalid OHLC)"
        )

    return result_df


def clean_csv_data(
    df: pd.DataFrame,
    instrument_prefix: Literal["GC", "DX"],
) -> pd.DataFrame:
    """
    Complete cleaning pipeline for OHLCV CSV data.

    Applies all cleaning steps:
    1. Filter to specified instrument prefix (GC or DX)
    2. Remove spread instruments
    3. Select highest volume contract per minute (skipping rows with zero/negative OHLC)
    4. Normalize symbol column to instrument prefix
    5. Sort by timestamp

    Args:
        df: Raw OHLCV DataFrame
        instrument_prefix: Instrument prefix to filter for ("GC" or "DX")

    Returns:
        Cleaned DataFrame ready for analysis with normalized symbols
    """
    logger.info(f"Starting cleaning pipeline for {instrument_prefix} data")
    logger.info(f"Input: {len(df)} rows, {df['ts_event'].nunique()} unique timestamps")

    if df.empty:
        logger.warning("Empty input DataFrame")
        return df

    # Step 1 & 2: Filter primary instruments with specified prefix
    df_filtered = filter_primary_instruments(df, prefix=instrument_prefix)

    if df_filtered.empty:
        logger.warning(f"No {instrument_prefix} instruments found after filtering")
        return df_filtered

    # Step 3: Select highest volume per minute (with OHLC validation)
    df_deduplicated = select_highest_volume_per_minute(df_filtered)

    # Step 4: Normalize symbol to instrument prefix
    df_deduplicated["symbol"] = instrument_prefix
    logger.info(f"Normalized all symbols to '{instrument_prefix}'")

    # Step 5: Sort by timestamp
    df_sorted = df_deduplicated.sort_values("ts_event").reset_index(drop=True)

    logger.info(
        f"Cleaning complete: {len(df_sorted)} rows, {df_sorted['ts_event'].nunique()} unique timestamps"
    )

    return df_sorted


def process_csv_file(
    input_path: Path,
    output_path: Path,
    instrument_prefix: Literal["GC", "DX"],
) -> None:
    """
    Process a CSV file through the cleaning pipeline.

    Args:
        input_path: Path to input CSV file
        output_path: Path to output CSV file
        instrument_prefix: Instrument prefix to filter for ("GC" or "DX")
    """
    logger.info(f"Processing {input_path}")

    # Read CSV
    try:
        df = pd.read_csv(input_path)
        logger.info(f"Loaded {len(df)} rows from {input_path}")
    except Exception as e:
        logger.error(f"Failed to read {input_path}: {e}")
        raise

    # Validate required columns
    required_columns = ["ts_event", "symbol", "open", "high", "low", "close", "volume"]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    # Clean data
    df_clean = clean_csv_data(df, instrument_prefix=instrument_prefix)

    # Save output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_clean.to_csv(output_path, index=False)
    logger.info(f"Saved {len(df_clean)} rows to {output_path}")

    # Log summary statistics
    if not df_clean.empty:
        logger.info(
            f"Date range: {df_clean['ts_event'].min()} to {df_clean['ts_event'].max()}"
        )
        logger.info(
            f"Symbol: {df_clean['symbol'].iloc[0]}"
        )  # All rows have same symbol now
        logger.info(f"Total volume: {df_clean['volume'].sum():,.0f}")


def main() -> None:
    """Main entry point for CLI usage."""
    parser = argparse.ArgumentParser(
        description="Clean OHLCV CSV data: remove spreads, filter instruments, select highest volume per minute",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process Gold (GC) data
  python scripts/clean_csv_data.py \\
    --input data/gc_dx_ohlcv/glbx_ohlcv_1m.csv \\
    --output data/gc_dx_ohlcv/GC_ohlcv-1m.csv \\
    --prefix GC

  # Process Dollar Index (DX) data
  python scripts/clean_csv_data.py \\
    --input data/gc_dx_ohlcv/dxy_ohlcv_1m.csv.csv \\
    --output data/gc_dx_ohlcv/DX_ohlcv-1m.csv \\
    --prefix DX
        """,
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to input CSV file",
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to output CSV file",
    )

    parser.add_argument(
        "--prefix",
        type=str,
        required=True,
        choices=["GC", "DX"],
        help="Instrument prefix to filter for (GC or DX)",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate input file exists
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        return

    # Process file
    process_csv_file(
        input_path=args.input,
        output_path=args.output,
        instrument_prefix=args.prefix,
    )

    logger.info("Processing complete!")


if __name__ == "__main__":
    main()

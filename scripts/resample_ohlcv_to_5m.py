"""Script to resample 1-minute OHLCV data to 5-minute bars.

This script reads 1-minute OHLCV CSV files and resamples them to 5-minute
timeframes using proper OHLCV aggregation rules:
- open: first value in period
- high: maximum value in period
- low: minimum value in period
- close: last value in period
- volume: sum of volume in period

Environment Variables:
    SCP_LOG_LEVEL: Override logging level (optional)

Usage:
    python scripts/resample_ohlcv_to_5m.py
"""

import sys
from pathlib import Path

import pandas as pd

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.config import load_config
from common.exceptions import DataSourceError
from common.logger import get_logger, setup_logging

# Initialize logging
logger = get_logger(__name__)

# Configuration
INPUT_FOLDER = "data/gc_dx_ohlcv"
OUTPUT_FOLDER = "data/gc_dx_ohlcv"
RESAMPLE_FREQUENCY = "5min"  # Target frequency


def resample_ohlcv(
    input_file: Path,
    output_file: Path,
    frequency: str = "5min",
) -> None:
    """Resample 1-minute OHLCV data to specified frequency.

    Args:
        input_file: Path to input CSV file with 1-minute data
        output_file: Path to save resampled CSV file
        frequency: Pandas frequency string (e.g., '5min', '15min', '1H')

    Raises:
        DataSourceError: If file read/write or resampling fails
    """
    try:
        logger.info(f"Reading 1-minute data from {input_file}")

        # Read CSV with timestamp as index
        df = pd.read_csv(
            input_file,
            index_col="ts_event",
            parse_dates=True,
        )

        if df.empty:
            logger.warning(f"Input file {input_file} is empty, skipping")
            return

        logger.info(f"Loaded {len(df)} 1-minute bars")
        logger.debug(f"Date range: {df.index.min()} to {df.index.max()}")

        # Define aggregation rules for OHLCV data
        agg_rules = {
            "open": "first",  # First value in period
            "high": "max",  # Maximum value in period
            "low": "min",  # Minimum value in period
            "close": "last",  # Last value in period
            "volume": "sum",  # Sum of volume in period
        }

        # Add other columns if they exist (keep first occurrence)
        for col in df.columns:
            if col not in agg_rules:
                if col in ["rtype", "publisher_id", "instrument_id", "symbol"]:
                    agg_rules[col] = "first"
                # Skip other columns

        # Resample to target frequency
        logger.info(f"Resampling to {frequency} bars")
        df_resampled = df.resample(frequency).agg(agg_rules)

        # Remove rows with NaN (periods with no data)
        df_resampled = df_resampled.dropna(subset=["open", "high", "low", "close"])

        logger.info(f"Resampled to {len(df_resampled)} {frequency} bars")

        # Ensure volume is integer
        if "volume" in df_resampled.columns:
            df_resampled["volume"] = df_resampled["volume"].fillna(0).astype(int)

        # Save to CSV
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df_resampled.to_csv(output_file)

        logger.info(f"Saved {len(df_resampled)} records to {output_file}")

    except FileNotFoundError as e:
        error_msg = f"Input file not found: {input_file}"
        logger.error(error_msg)
        raise DataSourceError(error_msg, cause=e) from e
    except Exception as e:
        error_msg = f"Failed to resample {input_file}: {e}"
        logger.error(error_msg)
        raise DataSourceError(error_msg, cause=e) from e


def main(
    input_folder: Path | None = None,
    output_folder: Path | None = None,
    frequency: str = RESAMPLE_FREQUENCY,
) -> None:
    """Main execution function to resample all 1-minute OHLCV files.

    Args:
        input_folder: Directory containing 1-minute CSV files (optional)
        output_folder: Directory to save resampled files (optional)
        frequency: Pandas frequency string for resampling (default: '5min')

    Raises:
        DataSourceError: If resampling fails
    """
    try:
        # Load config and setup logging
        config = load_config(PROJECT_ROOT / "config" / "core.yaml")
        setup_logging(config.system)

        logger.info("Starting OHLCV resampling script (5-minute)")

        # Determine folders
        if input_folder is None:
            input_folder = PROJECT_ROOT / INPUT_FOLDER
        if output_folder is None:
            output_folder = PROJECT_ROOT / OUTPUT_FOLDER

        logger.info(f"Input directory: {input_folder}")
        logger.info(f"Output directory: {output_folder}")
        logger.info(f"Resampling to: {frequency}")

        # Find all 1-minute OHLCV files
        pattern = "*_ohlcv-1m.csv"
        input_files = list(input_folder.glob(pattern))

        if not input_files:
            logger.warning(f"No 1-minute files found matching pattern: {pattern}")
            logger.info(
                "Run fetch_gc_dx_ohlcv_to_csv.py first to download 1-minute data"
            )
            return

        logger.info(f"Found {len(input_files)} 1-minute files to resample")

        # Process each file
        success_count = 0
        for input_file in input_files:
            try:
                # Generate output filename
                # Replace 'ohlcv-1m' with 'ohlcv-5m'
                output_filename = input_file.name.replace("ohlcv-1m", "ohlcv-5m")
                output_file = output_folder / output_filename

                logger.info(f"Processing: {input_file.name}")
                resample_ohlcv(
                    input_file=input_file,
                    output_file=output_file,
                    frequency=frequency,
                )
                success_count += 1

            except DataSourceError as e:
                logger.error(f"Failed to process {input_file.name}: {e}")
                # Continue with next file

        logger.info(
            f"Resampling complete: {success_count}/{len(input_files)} files processed"
        )

        if success_count == 0:
            logger.error("No files were successfully processed")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()






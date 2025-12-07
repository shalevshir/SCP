"""Script to fetch Gold (GC) and DXY OHLCV data from Databento and save to CSV.

This script retrieves historical OHLCV (Open, High, Low, Close, Volume) data
for Gold futures (GC) and DXY index at multiple timeframes and saves them to CSV files.

Environment Variables:
    DATABENTO_API_KEY: Databento API key (required)
    SCP_DATA_PATH: Override default data output directory (optional)

Usage:
    export DATABENTO_API_KEY="your-api-key"
    python scripts/fetch_gc_dx_ohlcv_to_csv.py
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from databento import Historical, DBNStore

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.exceptions import DataSourceError
from common.logger import get_logger, setup_logging
from common.config import load_config

# Initialize logging
logger = get_logger(__name__)

# === CONFIGURATION ===
DEST_FOLDER = "data/gc_dx_ohlcv"

# Symbols and dataset codes
# For futures, we need to use continuous contract notation
# See: https://databento.com/docs/knowledge-base/new-users/symbology?historical=python&live=python
GC_SYMBOL = "GC.FUT"  # Gold futures (continuous front month)
DXY_SYMBOL = "DX.FUT"  # US Dollar Index futures (continuous front month)
GC_DATASET = "GLBX.MDP3"  # CME Globex (MDP3 = Market Data Platform 3)
DXY_DATASET = "IFUS.IMPACT"  # ICE Futures US (IMPACT protocol)

# Timeframes to pull
# Available OHLCV schemas: ohlcv-1s, ohlcv-1m, ohlcv-1h, ohlcv-1d, ohlcv-eod
# Note: ohlcv-15m is NOT available from Databento
SCHEMAS: dict[str, str] = {
    "1s": "ohlcv-1s",    # 1-second bars
    "1m": "ohlcv-1m",    # 1-minute bars
    "1h": "ohlcv-1h",    # 1-hour bars (replaces 15m)
}


def check_dataset_info(client: Historical, dataset: str) -> None:
    """Check and log dataset availability information.
    
    Args:
        client: Databento Historical client
        dataset: Dataset to check (e.g., 'GLBX.MDP3')
    """
    try:
        # Get dataset date range
        date_range = client.metadata.get_dataset_range(dataset=dataset)
        logger.info(f"Dataset {dataset} available from {date_range['start_date']} to {date_range['end_date']}")
        
        # List available schemas
        schemas = client.metadata.list_schemas(dataset=dataset)
        logger.info(f"Available schemas: {', '.join(schemas)}")
    except Exception as e:
        logger.warning(f"Could not fetch metadata for {dataset}: {e}")


def get_api_key() -> str:
    """Retrieve Databento API key from environment variable.

    Returns:
        API key string

    Raises:
        ValueError: If DATABENTO_API_KEY environment variable is not set
    """
    return "db-J6huTVMhGFuND6594mMDS4cxbxUS6"
    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        raise ValueError(
            "DATABENTO_API_KEY environment variable is not set. "
            "Please set it with your Databento API key."
        )
    return api_key


def fetch_and_save(
    client: Historical,
    dataset: str,
    symbol: str,
    schema: str,
    start: datetime,
    end: datetime,
    output_folder: Path,
) -> None:
    """Fetch OHLCV data from Databento and save to CSV.

    Args:
        client: Initialized Databento Historical client
        dataset: Dataset identifier (e.g., 'GLBX.MDP3')
        symbol: Symbol to fetch (e.g., 'GC')
        schema: Schema identifier (e.g., 'ohlcv-1m')
        start: Start datetime for data range
        end: End datetime for data range
        output_folder: Directory to save CSV files

    Raises:
        DataSourceError: If data fetch or save fails
    """
    try:
        logger.info(
            f"Fetching {schema} data for {symbol} from {dataset} "
            f"({start.date()} to {end.date()})"
        )

        # Fetch data from Databento
        logger.debug(
            f"Query parameters: dataset={dataset}, symbol={symbol}, "
            f"schema={schema}, start={start}, end={end}"
        )
        
        dbn_data: DBNStore = client.timeseries.get_range(
            dataset=dataset,
            symbols=symbol,
            schema=schema,
            start=start,
            end=end,
            stype_in="parent",  # Use 'parent' symbology for continuous contracts
            stype_out="instrument_id",
        )

        # Convert DBNStore to DataFrame
        df = dbn_data.to_df()
        
        logger.info(f"Received {len(df)} records from Databento")

        if df.empty:
            logger.warning(
                f"No data returned for {symbol} {schema}. "
                f"This could mean: (1) No trading during this period, "
                f"(2) Symbol not found, or (3) Date range has no data."
            )
            return

        # Log DataFrame info for debugging
        logger.debug(f"DataFrame columns: {df.columns.tolist()}")
        logger.debug(f"DataFrame index: {df.index.name if hasattr(df.index, 'name') else 'unnamed'}")
        logger.debug(f"DataFrame shape: {df.shape}")
        logger.debug(f"First few rows:\n{df.head(2)}")

        # Handle timestamp - check if it's already in the index or in columns
        if df.index.name in ["ts_event", "timestamp", "ts_recv"] or isinstance(df.index, pd.DatetimeIndex):
            # Timestamp is already in the index
            logger.debug(f"Timestamp already in index: {df.index.name}")
            if not isinstance(df.index, pd.DatetimeIndex):
                # Convert to datetime if not already
                df.index = pd.to_datetime(df.index, unit="ns", utc=True)
        else:
            # Check which timestamp column exists in columns
            timestamp_col = None
            for col in ["ts_event", "timestamp", "ts_recv", "time"]:
                if col in df.columns:
                    timestamp_col = col
                    break
            
            if timestamp_col is None:
                # For OHLCV data, timestamp might not be present - index might be numeric
                # Try to use the existing index and see if it's a timestamp
                logger.warning(
                    f"No timestamp column found. Available columns: {df.columns.tolist()}, "
                    f"Index type: {type(df.index).__name__}"
                )
                # Assume index is already timestamp in nanoseconds
                try:
                    df.index = pd.to_datetime(df.index, unit="ns", utc=True)
                    df.index.name = "timestamp"
                    logger.info("Converted numeric index to timestamp")
                except Exception as e:
                    logger.error(f"Could not convert index to timestamp: {e}")
                    raise DataSourceError(
                        f"No timestamp found and could not convert index for {symbol}",
                        available_columns=df.columns.tolist(),
                        index_type=type(df.index).__name__
                    ) from e
            else:
                logger.debug(f"Using timestamp column: {timestamp_col}")
                df[timestamp_col] = pd.to_datetime(df[timestamp_col], unit="ns", utc=True)
                df = df.set_index(timestamp_col)

        # Build filename and save
        # Clean up symbol name for filename (remove .FUT suffix)
        clean_symbol = symbol.replace(".FUT", "").replace(".", "_")
        filename = f"{clean_symbol}_{schema}.csv"
        output_path = output_folder / filename
        df.to_csv(output_path)

        logger.info(
            f"Saved {len(df)} records for {symbol} {schema} to {output_path}"
        )

    except Exception as e:
        error_msg = f"Failed to fetch/save {schema} data for {symbol}: {e}"
        logger.error(error_msg)
        raise DataSourceError(error_msg, cause=e) from e


def main(
    days_back: int = 7,
    output_folder: Optional[Path] = None,
    data_delay_hours: int = 4,
    use_free_tier_dates: bool = False,
) -> None:
    """Main execution function to fetch GC and DXY OHLCV data.

    Args:
        days_back: Number of days of historical data to fetch (default: 7)
        output_folder: Override default output folder (optional)
        data_delay_hours: Hours to subtract from current time for data availability (default: 4)
        use_free_tier_dates: If True, fetch data from 60 days ago (free tier compatible) (default: False)

    Raises:
        ValueError: If API key is not configured
        DataSourceError: If data fetch fails
        
    Note:
        Historical market data typically has a 2-4 hour delay. The `data_delay_hours`
        parameter ensures we don't request data that isn't available yet.
        
        For free tier users: Recent data (last ~30 days) requires a paid subscription.
        Set `use_free_tier_dates=True` to fetch older data available on the free tier.
    """
    try:
        # Load config and setup logging
        config = load_config(PROJECT_ROOT / "config" / "core.yaml")
        setup_logging(config.system)

        logger.info("Starting Databento OHLCV data fetch script")

        # Get API key from environment
        api_key = get_api_key()

        # Initialize Databento client
        client = Historical(key=api_key)
        logger.info("Databento client initialized successfully")
        
        # Check dataset availability (helpful for debugging)
        logger.info("Checking dataset availability...")
        check_dataset_info(client, GC_DATASET)
        check_dataset_info(client, DXY_DATASET)

        # Determine output folder
        if output_folder is None:
            output_folder = PROJECT_ROOT / DEST_FOLDER
        output_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {output_folder}")

        # Calculate time range
        if use_free_tier_dates:
            # Free tier: Access to data older than ~30 days
            # Fetch data from 60 days ago to 40 days ago (safe range)
            end = datetime.utcnow() - timedelta(days=40)
            start = end - timedelta(days=days_back)
            logger.info(
                f"Using FREE TIER date range: {start.strftime('%Y-%m-%d %H:%M')} UTC to "
                f"{end.strftime('%Y-%m-%d %H:%M')} UTC "
                f"(Historical data, subscription not required)"
            )
        else:
            # Paid subscription: Access to recent data
            # Note: Historical data typically has a 2-4 hour delay
            # Set end time to N hours ago to ensure data availability
            end = datetime.utcnow() - timedelta(hours=data_delay_hours)
            start = end - timedelta(days=days_back)
            logger.info(
                f"Data time range: {start.strftime('%Y-%m-%d %H:%M')} UTC to "
                f"{end.strftime('%Y-%m-%d %H:%M')} UTC "
                f"(adjusted -{data_delay_hours}h for data availability)"
            )

        # Fetch data for both GC and DXY in all timeframes
        symbols_datasets = [
            (GC_SYMBOL, GC_DATASET),
            (DXY_SYMBOL, DXY_DATASET),
        ]

        total_fetches = len(symbols_datasets) * len(SCHEMAS)
        current_fetch = 0

        for symbol, dataset in symbols_datasets:
            for tf_name, schema in SCHEMAS.items():
                current_fetch += 1
                logger.info(f"Progress: {current_fetch}/{total_fetches}")

                fetch_and_save(
                    client=client,
                    dataset=dataset,
                    symbol=symbol,
                    schema=schema,
                    start=start,
                    end=end,
                    output_folder=output_folder,
                )

        logger.info(
            f"Successfully completed all {total_fetches} data fetches. "
            f"Files saved to {output_folder}"
        )

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except DataSourceError as e:
        logger.error(f"Data fetch error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch Gold (GC) and DXY OHLCV data from Databento"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYY-MM-DD format, e.g., 2024-07-01)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        help="End date (YYYY-MM-DD format, e.g., 2024-07-08)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=7,
        help="Days of data to fetch (ignored if start-date provided)",
    )
    parser.add_argument(
        "--free-tier",
        action="store_true",
        default=os.getenv("DATABENTO_FREE_TIER", "true").lower() == "true",
        help="Use free tier date range (60 days ago)",
    )
    
    args = parser.parse_args()
    
    # If custom dates provided, fetch them directly
    if args.start_date and args.end_date:
        try:
            config = load_config(PROJECT_ROOT / "config" / "core.yaml")
            setup_logging(config.system)
            logger = get_logger(__name__)
            
            start = datetime.strptime(args.start_date, "%Y-%m-%d")
            end = datetime.strptime(args.end_date, "%Y-%m-%d")
            
            logger.info(f"Starting Databento OHLCV data fetch script")
            logger.info(f"Custom date range: {start.date()} to {end.date()}")
            
            api_key = get_api_key()
            client = Historical(key=api_key)
            logger.info("Databento client initialized successfully")
            
            output_folder = PROJECT_ROOT / DEST_FOLDER
            output_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Output directory: {output_folder}")
            
            symbols_datasets = [(GC_SYMBOL, GC_DATASET), (DXY_SYMBOL, DXY_DATASET)]
            total_fetches = len(symbols_datasets) * len(SCHEMAS)
            current_fetch = 0
            
            for symbol, dataset in symbols_datasets:
                for tf_name, schema in SCHEMAS.items():
                    current_fetch += 1
                    logger.info(f"Progress: {current_fetch}/{total_fetches}")
                    fetch_and_save(client, dataset, symbol, schema, start, end, output_folder)
            
            logger.info(f"Successfully completed all {total_fetches} data fetches. Files saved to {output_folder}")
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)
            sys.exit(1)
    else:
        # Use the default main() function with relative dates
        main(
            days_back=args.days_back,
            use_free_tier_dates=args.free_tier
        )

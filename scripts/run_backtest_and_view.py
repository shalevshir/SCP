#!/usr/bin/env python3
"""Run backtest and launch results viewer.

This script provides an end-to-end workflow for:
1. Loading multi-timeframe data
2. Running backtest with specified parameters
3. Saving results to JSON
4. Launching interactive results viewer

Usage:
    # Run backtest and auto-launch viewer
    poetry run python scripts/run_backtest_and_view.py \
        --start 2025-07-01T10:00:00Z \
        --end 2025-07-31T13:00:00Z \
        --buffer-phase growth \
        --tier-active EarlyMild \
        --view

    # Just run backtest (save results only)
    poetry run python scripts/run_backtest_and_view.py \
        --start 2025-07-01T10:00:00Z \
        --end 2025-07-31T13:00:00Z \
        --no-view

    # View existing results
    poetry run python scripts/run_backtest_and_view.py \
        --load output/backtest_results_20250701.json \
        --view
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from backtester.replay_loop import BacktestReplayLoop, BacktestResults
from backtester.results_io import load_results, save_results
from common.config import load_config
from common.logger import get_logger, setup_logging
from dashboard.backtest_viewer import BacktestResultsViewer
from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer

logger = get_logger(__name__)


def parse_iso_datetime(value: str) -> datetime:
    """Parse ISO-8601 datetime strings, defaulting to UTC when tzinfo missing."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def detect_date_range_from_csv(data_dir: Path) -> tuple[datetime, datetime]:
    """Detect available date range from CSV files.

    Reads the first and last timestamps from GC 1m CSV file to determine
    the available date range. Uses efficient file reading to avoid loading
    entire large CSV files into memory.

    Args:
        data_dir: Directory containing CSV files

    Returns:
        Tuple of (start_datetime, end_datetime) in UTC

    Raises:
        FileNotFoundError: If required CSV files don't exist
        ValueError: If CSV files are empty or invalid
    """
    # Try different possible filenames for GC 1m data
    gc_files = [
        data_dir / "GC_ohlcv-1m.csv",
        data_dir / "glbx_ohlcv_1m.csv",
    ]
    
    gc_file = None
    for f in gc_files:
        if f.exists():
            gc_file = f
            break
    
    if gc_file is None:
        raise FileNotFoundError(
            f"Could not find GC 1m CSV file in {data_dir}. "
            f"Expected one of: {[str(f) for f in gc_files]}"
        )
    
    logger.info(f"Detecting date range from {gc_file}...")
    
    try:
        # Efficient method: read first row and last row only
        # Read first row
        df_first = pd.read_csv(gc_file, nrows=1)
        
        if df_first.empty:
            raise ValueError(f"CSV file {gc_file} has no data rows")
        
        # Get first timestamp
        if "ts_event" not in df_first.columns:
            raise ValueError(f"CSV file {gc_file} missing 'ts_event' column")
        
        first_ts = pd.to_datetime(df_first["ts_event"].iloc[0], utc=True).to_pydatetime()
        
        # For last row, read last N rows (efficient for large files)
        # Read last 100 rows to handle any trailing empty lines
        try:
            df_last = pd.read_csv(gc_file, usecols=["ts_event"]).tail(100)
            df_last["ts_event"] = pd.to_datetime(df_last["ts_event"], utc=True)
            df_last = df_last.sort_values("ts_event")
            
            # Get the actual last non-null timestamp
            last_ts = df_last["ts_event"].dropna().iloc[-1].to_pydatetime()
        except Exception:
            # Fallback: read entire file (slower but reliable)
            logger.warning("Could not detect last timestamp efficiently, reading full file...")
            df = pd.read_csv(gc_file, usecols=["ts_event"])
            df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
            df = df.sort_values("ts_event")
            last_ts = df["ts_event"].iloc[-1].to_pydatetime()
        
        logger.info(
            f"Detected date range: {first_ts.isoformat()} to {last_ts.isoformat()}"
        )
        
        return first_ts, last_ts
        
    except Exception as e:
        # Final fallback: read entire file
        logger.warning(f"Date detection failed, reading full file: {e}")
        try:
            df = pd.read_csv(gc_file, usecols=["ts_event"])
            df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True)
            df = df.sort_values("ts_event")
            
            if df.empty:
                raise ValueError(f"CSV file {gc_file} has no data")
            
            first_ts = df["ts_event"].iloc[0].to_pydatetime()
            last_ts = df["ts_event"].iloc[-1].to_pydatetime()
            
            logger.info(
                f"Detected date range: {first_ts.isoformat()} to {last_ts.isoformat()}"
            )
            
            return first_ts, last_ts
        except Exception as e2:
            raise ValueError(
                f"Failed to detect date range from {gc_file}: {e2}"
            ) from e2


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Run backtest and launch results viewer"
    )
    
    # Data loading
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/gc_dx_ohlcv"),
        help="Directory containing GC/DX CSV files (default: data/gc_dx_ohlcv)",
    )
    
    # Date range (for new backtest)
    parser.add_argument(
        "--start",
        type=parse_iso_datetime,
        help="Start datetime (ISO-8601, e.g., 2025-07-01T10:00:00Z). If not provided, uses first timestamp from CSV files.",
    )
    parser.add_argument(
        "--end",
        type=parse_iso_datetime,
        help="End datetime (ISO-8601, e.g., 2025-07-31T13:00:00Z). If not provided, uses last timestamp from CSV files.",
    )
    
    # Load existing results
    parser.add_argument(
        "--load",
        type=Path,
        help="Load existing results from JSON file",
    )
    
    # Backtest parameters
    parser.add_argument(
        "--buffer-phase",
        type=str,
        default="growth",
        choices=["startup", "growth", "scaling", "institutional"],
        help="Capital buffer phase (default: growth)",
    )
    parser.add_argument(
        "--tier-active",
        type=str,
        default="EarlyMild",
        choices=["Conservative", "EarlyMild", "Mild", "Offensive"],
        help="Active enforcer tier (default: EarlyMild)",
    )
    parser.add_argument(
        "--htf-approach",
        type=str,
        choices=["streaming", "vectorized"],
        default="streaming",
        help="HTF feature computation approach (default: streaming)",
    )
    
    # Output
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory for results (default: output/)",
    )
    parser.add_argument(
        "--output-file",
        type=Path,
        help="Output filename for results JSON (default: auto-generated)",
    )
    
    # Viewer options
    parser.add_argument(
        "--view",
        action="store_true",
        default=True,
        help="Launch results viewer after backtest (default: True)",
    )
    parser.add_argument(
        "--no-view",
        action="store_false",
        dest="view",
        help="Don't launch viewer (just save results)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8051,
        help="Port for results viewer (default: 8051)",
    )
    
    return parser


def run_backtest(
    data_dir: Path,
    start: datetime,
    end: datetime,
    buffer_phase: str,
    tier_active: str,
    htf_approach: str,
    output_file: Path | None = None,
) -> tuple[BacktestResults, Path]:
    """Run backtest and return results.

    Args:
        data_dir: Directory containing CSV data files
        start: Start datetime
        end: End datetime
        buffer_phase: Capital buffer phase
        tier_active: Active enforcer tier
        htf_approach: HTF computation approach
        output_file: Optional output file path

    Returns:
        Tuple of (BacktestResults, output_file_path)
    """
    logger.info("=" * 80)
    logger.info("Running Backtest")
    logger.info("=" * 80)
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Date range: {start} to {end}")
    logger.info(f"Buffer phase: {buffer_phase}")
    logger.info(f"Tier active: {tier_active}")
    logger.info(f"HTF approach: {htf_approach}")

    # Load multi-timeframe data
    logger.info("\nLoading multi-timeframe data...")
    sync_layer = MultiTimeframeSyncLayer(str(data_dir))
    multi_tf_data = sync_layer.load(start, end)

    logger.info(
        f"Loaded {len(multi_tf_data)} synchronized bars "
        f"from {multi_tf_data.execution_timestamps[0]} "
        f"to {multi_tf_data.execution_timestamps[-1]}"
    )

    # Define market state
    market_state = {
        "buffer_phase": buffer_phase,
        "tier_active": tier_active,
        "ceo_directive_active": True,
        "news_ok": True,
        "session_ok": True,
    }

    # Define risk config
    risk_per_trade_map = {
        "startup": 350.0,
        "growth": 600.0,
        "scaling": 1000.0,
        "institutional": 1200.0,
    }
    
    max_contracts_map = {
        "startup": 1,
        "growth": 1,
        "scaling": 2,
        "institutional": 3,
    }

    risk_config = {
        "risk_per_trade": risk_per_trade_map.get(buffer_phase, 600.0),
        "buffer_phase": buffer_phase,
        "max_contracts": max_contracts_map.get(buffer_phase, 1),
    }

    # Run backtest
    logger.info("\nRunning backtest replay loop...")
    loop = BacktestReplayLoop(
        multi_tf_data=multi_tf_data,
        timeframe="1m",
        market_state=market_state,
        risk_config=risk_config,
        htf_approach=htf_approach,
        log_signals=False,
    )

    results = loop.run()

    # Generate output filename if not provided
    if output_file is None:
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"backtest_results_{start_str}_{end_str}.json"

    # Save results
    logger.info(f"\nSaving results to {output_file}...")
    save_results(results, output_file)

    logger.info("\n" + "=" * 80)
    logger.info("Backtest Complete!")
    logger.info("=" * 80)
    logger.info(f"Total trades: {results.total_trades}")
    logger.info(f"Win rate: {results.win_rate:.1f}%")
    logger.info(f"Total PnL: {results.total_pnl:.2f} points")
    if results.total_pnl_dollars:
        logger.info(f"Total PnL: ${results.total_pnl_dollars:.2f}")
    logger.info(f"Average R: {results.average_r:.2f}R")

    return results, output_file


def load_gc_data_for_viewer(data_dir: Path, start: datetime, end: datetime) -> pd.DataFrame | None:
    """Load GC data for price chart visualization.

    Args:
        data_dir: Directory containing CSV files
        start: Start datetime
        end: End datetime

    Returns:
        GC DataFrame or None if not available
    """
    try:
        from data_layer.loader import HistoricalDataLoader

        loader = HistoricalDataLoader(data_dir)
        data = loader.load(["GC"], "1m", start, end)
        
        if "GC" in data and not data["GC"].empty:
            df = data["GC"]
            # Ensure timestamp column exists for chart
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.copy()
                df["timestamp"] = df.index
            elif "timestamp" not in df.columns:
                logger.warning("GC DataFrame missing timestamp column/index")
                return None
            return df
    except Exception as e:
        logger.warning(f"Could not load GC data for viewer: {e}")
    
    return None


def main() -> None:
    """Main entry point."""
    # Initialize logging first
    project_root = Path(__file__).parent.parent
    config = load_config(project_root / "config" / "core.yaml")
    setup_logging(config.system)
    
    parser = build_arg_parser()
    args = parser.parse_args()

    # Validate arguments
    if args.load:
        # Load existing results
        if not args.load.exists():
            logger.error(f"Results file not found: {args.load}")
            sys.exit(1)

        logger.info(f"Loading results from {args.load}...")
        results = load_results(args.load)

        if args.view:
            logger.info("Launching results viewer...")
            viewer = BacktestResultsViewer(results)
            viewer.run(port=args.port)
        else:
            logger.info("Results loaded. Use --view to launch viewer.")

    else:
        # Run new backtest
        # Auto-detect date range if not provided
        if args.start is None or args.end is None:
            logger.info("Start/end dates not provided, detecting from CSV files...")
            try:
                detected_start, detected_end = detect_date_range_from_csv(args.data_dir)
                if args.start is None:
                    args.start = detected_start
                    logger.info(f"Using detected start: {args.start.isoformat()}")
                if args.end is None:
                    args.end = detected_end
                    logger.info(f"Using detected end: {args.end.isoformat()}")
            except Exception as e:
                logger.error(f"Failed to detect date range: {e}")
                logger.error("Please provide --start and --end dates manually")
                sys.exit(1)

        if not args.data_dir.exists():
            logger.error(f"Data directory not found: {args.data_dir}")
            sys.exit(1)

        # Ensure output directory exists
        args.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Run backtest
        results, output_file = run_backtest(
            data_dir=args.data_dir,
            start=args.start,
            end=args.end,
            buffer_phase=args.buffer_phase,
            tier_active=args.tier_active,
            htf_approach=args.htf_approach,
            output_file=args.output_file or (args.output_dir / f"backtest_results_{args.start.strftime('%Y%m%d')}_{args.end.strftime('%Y%m%d')}.json"),
        )

        # Launch viewer if requested
        if args.view:
            logger.info("\nLaunching results viewer...")
            
            # Try to load GC data for price chart
            gc_df = load_gc_data_for_viewer(args.data_dir, args.start, args.end)
            
            viewer = BacktestResultsViewer(results, gc_df=gc_df)
            viewer.run(port=args.port)


if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""Run the Shir Capital Live Dashboard.

This script launches the trading simulation dashboard with configurable
data range, warmup period, and simulation speed.

Usage:
    uv run python scripts/run_dashboard.py --help

Examples:
    # Quick test (no multi-day warmup)
    uv run python scripts/run_dashboard.py \\
        --data-dir ./data/gc_dx_ohlcv/ \\
        --start-date 2025-07-01 \\
        --end-date 2025-07-02 \\
        --speed 10.0

    # Production (1 day warmup)
    uv run python scripts/run_dashboard.py \\
        --data-dir ./data/gc_dx_ohlcv/ \\
        --start-date 2025-07-02 \\
        --end-date 2025-07-03 \\
        --start-time "2025-07-02 10:00:00" \\
        --warmup-days 1 \\
        --speed 5.0

    # Continuous mode (no auto-pause)
    uv run python scripts/run_dashboard.py \\
        --data-dir ./data/gc_dx_ohlcv/ \\
        --start-date 2025-07-01 \\
        --end-date 2025-07-02 \\
        --no-auto-pause \\
        --speed 30.0
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from common.logger import get_logger
from dashboard.app import LiveDashboard
from dashboard.core.data_stream import DataStream
from dashboard.core.engine import SimulationEngine
from validation.config_loader import load_session_config
from validation.engine import ValidationEngine
from validation.session_validator import SessionValidator

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Shir Capital Live Trading Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Data configuration
    parser.add_argument(
        "--data-dir",
        type=str,
        default="./data/gc_dx_ohlcv/",
        help="Path to historical data directory (default: ./data/gc_dx_ohlcv/)",
    )

    # Date range
    parser.add_argument(
        "--start-date",
        type=str,
        required=True,
        help="Start date for simulation (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        required=True,
        help="End date for simulation (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--start-time",
        type=str,
        default=None,
        help="Specific start time for display (YYYY-MM-DD HH:MM:SS). "
        "Defaults to start-date 10:00:00 if not specified.",
    )

    # Warmup configuration
    parser.add_argument(
        "--warmup-days",
        type=int,
        default=0,
        help="Number of additional days before start-date to load for HTF warmup. "
        "Recommended: 1 for production accuracy. (default: 0)",
    )

    # Simulation configuration
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Simulation speed multiplier (default: 1.0 = realtime)",
    )
    parser.add_argument(
        "--no-auto-pause",
        action="store_true",
        help="Disable auto-pause on A+ signals",
    )

    # Server configuration
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Dashboard host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8050,
        help="Dashboard port (default: 8050)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Dash debug mode",
    )

    return parser.parse_args()


def parse_date(date_str: str) -> datetime:
    """Parse date string to timezone-aware datetime."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.replace(tzinfo=timezone.utc)


def parse_datetime(datetime_str: str) -> datetime:
    """Parse datetime string to timezone-aware datetime."""
    dt = datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)


def main() -> None:
    """Main entry point."""
    args = parse_args()

    logger.info("=" * 60)
    logger.info("Shir Capital Live Trading Dashboard")
    logger.info("=" * 60)

    # Parse dates
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)

    # Determine start time for display
    if args.start_time:
        start_time = parse_datetime(args.start_time)
    else:
        # Default to 10:00 AM (session start)
        start_time = start_date.replace(hour=10, minute=0, second=0)

    logger.info(f"Simulation date range: {start_date.date()} to {end_date.date()}")
    logger.info(f"Display start time: {start_time}")

    # Calculate data load start (for multi-day warmup)
    warmup_days = args.warmup_days
    data_load_start = start_date

    if warmup_days > 0:
        data_load_start = start_date - timedelta(days=warmup_days)
        logger.info(
            f"Loading {warmup_days} additional day(s) for HTF warmup: "
            f"{data_load_start.date()} to {start_date.date()}"
        )

    # Validate data directory
    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        sys.exit(1)

    # Initialize data stream
    logger.info("Initializing data stream...")
    data_stream = DataStream(str(data_dir))

    # Load data (including warmup days)
    loaded_count = data_stream.load(data_load_start, end_date, timeframe="1m")
    if loaded_count == 0:
        logger.error("No data loaded. Check date range and data files.")
        sys.exit(1)

    # Seek to display start time
    try:
        data_stream.seek_to_timestamp(start_time)
    except ValueError as e:
        logger.error(f"Failed to seek to start time: {e}")
        sys.exit(1)

    # Log warmup info
    warmup_bars = data_stream.warmup_bars
    warmup_hours = warmup_bars / 60
    logger.info(
        f"Warmup context: {warmup_bars:,} bars ({warmup_hours:.1f} hours)"
    )

    if warmup_hours < 1.0:
        logger.warning(
            f"Low warmup data ({warmup_hours:.1f} hours). "
            "Consider using --warmup-days 1 for better HTF accuracy."
        )
    elif warmup_hours >= 24:
        logger.info(
            f"Excellent! {warmup_hours / 24:.1f} days of warmup data available."
        )

    # Initialize validators
    logger.info("Initializing validators...")
    session_config = load_session_config()
    validation_engine = ValidationEngine()
    session_validator = SessionValidator(session_config)

    # Initialize simulation engine
    logger.info("Initializing simulation engine...")
    engine = SimulationEngine(
        data_stream=data_stream,
        validation_engine=validation_engine,
        session_validator=session_validator,
        auto_pause_on_a_plus=not args.no_auto_pause,
        speed_multiplier=args.speed,
    )

    # Run warmup phase (synchronous, before dashboard starts)
    logger.info("Running warmup phase...")
    engine.warmup()

    # Create dashboard
    logger.info("Creating dashboard...")
    dashboard = LiveDashboard(engine)

    # Launch
    logger.info(f"Starting dashboard at http://{args.host}:{args.port}")
    logger.info(f"Simulation speed: {args.speed}x")
    logger.info(f"Auto-pause on A+ signals: {not args.no_auto_pause}")
    logger.info("=" * 60)

    try:
        dashboard.run(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        logger.info("Dashboard stopped by user")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()

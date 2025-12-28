#!/usr/bin/env python3
"""Collect trades from microservices PostgreSQL database.

This script queries the trades table in TimescaleDB and converts the results
to a format compatible with backtester Trade objects for comparison.

Usage:
    # Collect all trades
    poetry run python scripts/collect_microservice_trades.py \
        --output output/microservices_trades.json

    # Collect trades for specific date range
    poetry run python scripts/collect_microservice_trades.py \
        --start 2024-11-01 --end 2024-11-30 \
        --output output/microservices_trades_nov.json

    # Custom database URL
    poetry run python scripts/collect_microservice_trades.py \
        --database-url postgresql://scp:password@localhost:5432/scp \
        --output output/microservices_trades.json
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from scp_shared.database import DatabasePool

from common.logger import get_logger, setup_logging
from common.config import load_config

logger = get_logger(__name__)


def parse_iso_datetime(value: str) -> datetime:
    """Parse ISO-8601 datetime strings, defaulting to UTC when tzinfo missing."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def collect_trades(
    database_url: str,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict]:
    """Collect trades from PostgreSQL database.
    
    Args:
        database_url: PostgreSQL connection URL
        start: Optional start datetime for filtering
        end: Optional end datetime for filtering
        
    Returns:
        List of trade dictionaries in backtester-compatible format
    """
    logger.info("=" * 80)
    logger.info("Collecting Microservices Trades")
    logger.info("=" * 80)
    logger.info(f"Database URL: {database_url}")
    
    if start:
        logger.info(f"Start filter: {start}")
    if end:
        logger.info(f"End filter: {end}")
    
    # Connect to database
    logger.info("\nConnecting to database...")
    pool = DatabasePool(database_url)
    
    try:
        await pool.connect()
        logger.info("Connected to database successfully")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise
    
    # Build query
    query = """
        SELECT
            id,
            signal_id,
            direction,
            setup_type,
            entry_price,
            sl_price,
            tp_price,
            quantity,
            opened_at,
            closed_at,
            exit_price,
            exit_reason,
            pnl_points,
            pnl_dollars,
            r_multiple,
            state,
            confirmations,
            transition_history
        FROM trades
        WHERE 1=1
    """
    
    params = []
    if start:
        query += " AND opened_at >= $" + str(len(params) + 1)
        params.append(start)
    
    if end:
        query += " AND opened_at < $" + str(len(params) + 1)
        params.append(end)
    
    query += " ORDER BY opened_at"
    
    logger.info(f"\nExecuting query with {len(params)} parameters...")
    
    try:
        rows = await pool.fetch(query, *params)
        logger.info(f"Retrieved {len(rows)} trades from database")
    except Exception as e:
        logger.error(f"Failed to query trades: {e}")
        await pool.close()
        raise
    
    await pool.close()
    
    # Convert to backtester-compatible format
    logger.info("\nConverting trades to backtester format...")
    trades = []
    
    for row in rows:
        # Convert database row to dict
        trade_dict = {
            "trade_id": str(row["id"]),
            "symbol": "GC",  # Hardcoded for now (can be added to DB schema later)
            "timeframe": "1m",
            "direction": row["direction"],
            "setup_type": row["setup_type"],
            "entry_timestamp": row["opened_at"].isoformat() if row["opened_at"] else None,
            "entry_price": float(row["entry_price"]) if row["entry_price"] else None,
            "stop_loss": float(row["sl_price"]) if row["sl_price"] else None,
            "take_profit": float(row["tp_price"]) if row["tp_price"] else None,
            "contracts": int(row["quantity"]) if row["quantity"] else 1,
            "exit_timestamp": row["closed_at"].isoformat() if row["closed_at"] else None,
            "exit_price": float(row["exit_price"]) if row["exit_price"] else None,
            "exit_reason": row["exit_reason"],
            "pnl": float(row["pnl_points"]) if row["pnl_points"] else None,
            "pnl_dollars": float(row["pnl_dollars"]) if row["pnl_dollars"] else None,
            "r_realized": float(row["r_multiple"]) if row["r_multiple"] else None,
            "status": row["state"],
            "confirmations": row["confirmations"],
            "transition_history": row["transition_history"],
        }
        
        trades.append(trade_dict)
    
    logger.info(f"Converted {len(trades)} trades")
    
    # Summary statistics
    if trades:
        open_trades = sum(1 for t in trades if t["status"] == "OPEN")
        closed_trades = sum(1 for t in trades if t["status"] == "CLOSED")
        
        logger.info("\nTrade Summary:")
        logger.info(f"  Total: {len(trades)}")
        logger.info(f"  Open: {open_trades}")
        logger.info(f"  Closed: {closed_trades}")
        
        # Direction breakdown
        long_trades = sum(1 for t in trades if t["direction"] == "long")
        short_trades = sum(1 for t in trades if t["direction"] == "short")
        logger.info(f"  Long: {long_trades}")
        logger.info(f"  Short: {short_trades}")
        
        # Setup type breakdown
        setup_types = {}
        for t in trades:
            setup = t.get("setup_type", "UNKNOWN")
            setup_types[setup] = setup_types.get(setup, 0) + 1
        
        logger.info("\nSetup Types:")
        for setup, count in sorted(setup_types.items()):
            logger.info(f"  {setup}: {count}")
    
    return trades


def save_trades(trades: list[dict], output_file: Path) -> None:
    """Save trades to JSON file.
    
    Args:
        trades: List of trade dictionaries
        output_file: Output file path
    """
    logger.info(f"\nSaving trades to {output_file}...")
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        "metadata": {
            "collected_at": datetime.now(UTC).isoformat(),
            "total_trades": len(trades),
        },
        "trades": trades,
    }
    
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)
    
    logger.info(f"Saved {len(trades)} trades to {output_file}")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Collect trades from microservices PostgreSQL database"
    )
    
    # Database connection
    parser.add_argument(
        "--database-url",
        type=str,
        default="postgresql://scp:scp_dev_password@localhost:5432/scp",
        help="PostgreSQL connection URL (default: postgresql://scp:scp_dev_password@localhost:5432/scp)",
    )
    
    # Date range filters
    parser.add_argument(
        "--start",
        type=parse_iso_datetime,
        help="Start datetime filter (ISO-8601, e.g., 2024-11-01T00:00:00Z)",
    )
    parser.add_argument(
        "--end",
        type=parse_iso_datetime,
        help="End datetime filter (ISO-8601, e.g., 2024-11-30T23:59:59Z)",
    )
    
    # Output
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/microservices_trades.json"),
        help="Output file path (default: output/microservices_trades.json)",
    )
    
    return parser


async def main() -> None:
    """Main entry point."""
    # Initialize logging
    project_root = Path(__file__).parent.parent
    config = load_config(project_root / "config" / "core.yaml")
    setup_logging(config.system)
    
    parser = build_arg_parser()
    args = parser.parse_args()
    
    try:
        # Collect trades
        trades = await collect_trades(
            database_url=args.database_url,
            start=args.start,
            end=args.end,
        )
        
        # Save to file
        save_trades(trades, args.output)
        
        logger.info("\n" + "=" * 80)
        logger.info("Collection Complete!")
        logger.info("=" * 80)
        sys.exit(0)
    
    except Exception as e:
        logger.error(f"\nCollection failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


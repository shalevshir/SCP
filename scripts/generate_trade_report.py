#!/usr/bin/env python3
"""Generate trade report with features and HTF information from database.

This script queries all trades from the database and enriches them with
features and HTF bias data at the time of entry, similar to the backtest
output format.

Usage:
    poetry run python scripts/generate_trade_report.py [OPTIONS]

Options:
    --output FILE           Output report JSON path (default: output/trade_report_<timestamp>.json)
    --db-url URL            Database connection URL (default: from DATABASE_URL env var)
    --start DATE            Start date filter (YYYY-MM-DD, optional)
    --end DATE              End date filter (YYYY-MM-DD, optional)

Example:
    poetry run python scripts/generate_trade_report.py \
        --output output/trade_report.json \
        --start 2025-01-01 \
        --end 2025-01-31
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
# Add shared library to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "shared" / "src"))

from common.logger import get_logger

logger = get_logger(__name__)


async def query_all_trades(
    conn: asyncpg.Connection,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    """Query all trades from database.

    Args:
        conn: Database connection
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of trade dictionaries
    """
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
            transition_history,
            entry_bar_idx,
            reached_1r,
            created_at,
            updated_at
        FROM trades
        WHERE 1=1
    """

    params: list[Any] = []
    param_idx = 1

    if start_date:
        query += f" AND opened_at >= ${param_idx}"
        params.append(start_date)
        param_idx += 1

    if end_date:
        query += f" AND opened_at <= ${param_idx}"
        params.append(end_date)
        param_idx += 1

    query += " ORDER BY opened_at ASC"

    rows = await conn.fetch(query, *params)

    trades = []
    for row in rows:
        trade = {
            "id": str(row["id"]),
            "signal_id": str(row["signal_id"]),
            "direction": row["direction"],
            "setup_type": row["setup_type"],
            "entry_price": float(row["entry_price"]),
            "sl_price": float(row["sl_price"]),
            "tp_price": float(row["tp_price"]),
            "quantity": row["quantity"],
            "opened_at": row["opened_at"].isoformat() if row["opened_at"] else None,
            "closed_at": row["closed_at"].isoformat() if row["closed_at"] else None,
            "exit_price": float(row["exit_price"]) if row["exit_price"] else None,
            "exit_reason": row["exit_reason"],
            "pnl_points": float(row["pnl_points"]) if row["pnl_points"] else None,
            "pnl_dollars": float(row["pnl_dollars"]) if row["pnl_dollars"] else None,
            "r_multiple": float(row["r_multiple"]) if row["r_multiple"] else None,
            "state": row["state"],
            "confirmations": row["confirmations"] if row["confirmations"] else {},
            "transition_history": (
                row["transition_history"] if row["transition_history"] else {}
            ),
            "entry_bar_idx": row["entry_bar_idx"],
            "reached_1r": row["reached_1r"] if row["reached_1r"] is not None else False,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }
        trades.append(trade)

    return trades


async def query_features_at_timestamp(
    conn: asyncpg.Connection,
    timestamp: datetime,
    symbol: str = "GC",
    timeframe: str = "1m",
) -> dict | None:
    """Query features from database at specific timestamp.

    Args:
        conn: Database connection
        timestamp: Timestamp to query
        symbol: Symbol to query (default: "GC")
        timeframe: Timeframe to query (default: "1m")

    Returns:
        Features dictionary or None if not found
    """
    query = """
        SELECT 
            timestamp,
            symbol,
            timeframe,
            close,
            vwap,
            rsi,
            ema_9,
            ema_20,
            ema_50,
            dxy_correlation,
            structure_label,
            vwap_deviation
        FROM features
        WHERE timestamp <= $1
          AND symbol = $2
          AND timeframe = $3
        ORDER BY timestamp DESC
        LIMIT 1
    """

    row = await conn.fetchrow(query, timestamp, symbol, timeframe)

    if row is None:
        return None

    return {
        "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
        "symbol": row["symbol"],
        "timeframe": row["timeframe"],
        "close": float(row["close"]) if row["close"] else None,
        "vwap": float(row["vwap"]) if row["vwap"] else None,
        "rsi": float(row["rsi"]) if row["rsi"] else None,
        "ema_9": float(row["ema_9"]) if row["ema_9"] else None,
        "ema_20": float(row["ema_20"]) if row["ema_20"] else None,
        "ema_50": float(row["ema_50"]) if row["ema_50"] else None,
        "dxy_correlation": (
            float(row["dxy_correlation"]) if row["dxy_correlation"] else None
        ),
        "structure_label": row["structure_label"],
        "vwap_deviation": (
            float(row["vwap_deviation"]) if row["vwap_deviation"] else None
        ),
    }


async def query_htf_bias_at_timestamp(
    conn: asyncpg.Connection,
    timestamp: datetime,
) -> dict | None:
    """Query HTF bias from database at specific timestamp.

    Args:
        conn: Database connection
        timestamp: Timestamp to query

    Returns:
        HTF bias dictionary or None if not found
    """
    query = """
        SELECT 
            timestamp,
            bias,
            score,
            confidence,
            structure_15m,
            structure_1h,
            dxy_aligned,
            chop_detected,
            seasonality_adjustment,
            seasonality_period,
            vwap_trend_confirmed
        FROM htf_bias_history
        WHERE timestamp <= $1
        ORDER BY timestamp DESC
        LIMIT 1
    """

    row = await conn.fetchrow(query, timestamp)

    if row is None:
        return None

    return {
        "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
        "bias": row["bias"],
        "score": float(row["score"]) if row["score"] else None,
        "confidence": row["confidence"],
        "structure_15m": row["structure_15m"],
        "structure_1h": row["structure_1h"],
        "dxy_aligned": row["dxy_aligned"],
        "chop_detected": row["chop_detected"],
        "seasonality_adjustment": (
            float(row["seasonality_adjustment"])
            if row["seasonality_adjustment"]
            else None
        ),
        "seasonality_period": row["seasonality_period"],
        "vwap_trend_confirmed": (
            row["vwap_trend_confirmed"]
            if row["vwap_trend_confirmed"] is not None
            else False
        ),
    }


async def enrich_trade_with_data(
    conn: asyncpg.Connection,
    trade: dict,
) -> dict:
    """Enrich a trade with features and HTF bias data.

    Args:
        conn: Database connection
        trade: Trade dictionary

    Returns:
        Enriched trade dictionary
    """
    # Parse entry timestamp
    opened_at_str = trade["opened_at"]
    if not opened_at_str:
        logger.warning(f"Trade {trade['id']} has no opened_at timestamp")
        return trade

    opened_at = datetime.fromisoformat(opened_at_str.replace("Z", "+00:00"))

    # Query features at entry time
    features = await query_features_at_timestamp(
        conn, opened_at, symbol="GC", timeframe="1m"
    )

    # Query HTF bias at entry time
    htf_bias = await query_htf_bias_at_timestamp(conn, opened_at)

    # Build enriched trade structure similar to backtest output
    enriched_trade = {
        "trade_id": trade["id"],
        "signal_id": trade["signal_id"],
        "entry_timestamp": trade["opened_at"],
        "exit_timestamp": trade["closed_at"],
        "direction": trade["direction"],
        "setup_type": trade["setup_type"],
        "entry_price": trade["entry_price"],
        "sl_price": trade["sl_price"],
        "tp_price": trade["tp_price"],
        "exit_price": trade["exit_price"],
        "quantity": trade["quantity"],
        "pnl_points": trade["pnl_points"],
        "pnl_dollars": trade["pnl_dollars"],
        "r_multiple": trade["r_multiple"],
        "exit_reason": trade["exit_reason"],
        "state": trade["state"],
        "entry_bar_idx": trade["entry_bar_idx"],
        "reached_1r": trade["reached_1r"],
        "confirmations": trade["confirmations"],
        "transition_history": trade["transition_history"],
        "features": features,
        "htf_bias": htf_bias,
    }

    return enriched_trade


async def generate_report(
    db_url: str,
    output_file: Path,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> None:
    """Generate trade report from database.

    Args:
        db_url: Database connection URL
        output_file: Output file path
        start_date: Optional start date filter
        end_date: Optional end date filter
    """
    logger.info(f"Connecting to database...")
    conn = await asyncpg.connect(db_url)

    try:
        logger.info("Querying trades from database...")
        trades = await query_all_trades(conn, start_date, end_date)
        logger.info(f"Found {len(trades)} trades")

        if len(trades) == 0:
            logger.warning("No trades found in database")
            return

        # Enrich each trade with features and HTF bias
        enriched_trades = []
        for i, trade in enumerate(trades, 1):
            logger.info(
                f"Processing trade {i}/{len(trades)}: {trade['id']} ({trade['opened_at']})"
            )
            enriched_trade = await enrich_trade_with_data(conn, trade)
            enriched_trades.append(enriched_trade)

        # Calculate summary metrics
        closed_trades = [t for t in enriched_trades if t["state"] == "CLOSED"]
        winning_trades = [
            t for t in closed_trades if t["pnl_points"] and t["pnl_points"] > 0
        ]
        losing_trades = [
            t for t in closed_trades if t["pnl_points"] and t["pnl_points"] <= 0
        ]

        total_pnl_points = sum(t["pnl_points"] or 0 for t in closed_trades)
        total_pnl_dollars = sum(t["pnl_dollars"] or 0 for t in closed_trades)
        win_rate = (
            (len(winning_trades) / len(closed_trades) * 100) if closed_trades else 0.0
        )

        avg_r = (
            sum(t["r_multiple"] or 0 for t in closed_trades) / len(closed_trades)
            if closed_trades
            else 0.0
        )

        # Build report structure similar to backtest output
        report = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_trades": len(enriched_trades),
                "closed_trades": len(closed_trades),
                "open_trades": len(
                    [t for t in enriched_trades if t["state"] == "OPEN"]
                ),
                "invalidated_trades": len(
                    [t for t in enriched_trades if t["state"] == "INVALIDATED"]
                ),
            },
            "metrics": {
                "total_pnl_points": total_pnl_points,
                "total_pnl_dollars": total_pnl_dollars,
                "win_rate": win_rate,
                "total_trades": len(closed_trades),
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
                "average_r": avg_r,
            },
            "trades": enriched_trades,
        }

        # Write to file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Report saved to {output_file}")
        logger.info(
            f"Summary: {len(enriched_trades)} trades, "
            f"{len(closed_trades)} closed, "
            f"Win rate: {win_rate:.1f}%, "
            f"Total PnL: ${total_pnl_dollars:.2f}"
        )

    finally:
        await conn.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate trade report with features and HTF information from database"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output report JSON path (default: output/trade_report_<timestamp>.json)",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Database connection URL (default: from DATABASE_URL env var)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=None,
        help="Start date filter (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=None,
        help="End date filter (YYYY-MM-DD)",
    )

    args = parser.parse_args()

    # Get database URL
    db_url = args.db_url or os.environ.get("DATABASE_URL")
    if not db_url:
        db_url = "postgresql://scp:scp_dev_password@localhost:5432/scp"
        logger.warning(f"Using default database URL: {mask_connection_url(db_url)}")
    else:
        logger.info(f"Using database URL: {mask_connection_url(db_url)}")

    # Parse date filters
    start_date = None
    if args.start:
        try:
            start_date = datetime.strptime(args.start, "%Y-%m-%d")
        except ValueError:
            logger.error(f"Invalid start date format: {args.start}. Use YYYY-MM-DD")
            return 1

    end_date = None
    if args.end:
        try:
            end_date = datetime.strptime(args.end, "%Y-%m-%d")
            # Set to end of day
            end_date = end_date.replace(hour=23, minute=59, second=59)
        except ValueError:
            logger.error(f"Invalid end date format: {args.end}. Use YYYY-MM-DD")
            return 1

    # Determine output file
    if args.output:
        output_file = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path(f"output/trade_report_{timestamp}.json")

    # Run async function
    try:
        asyncio.run(generate_report(db_url, output_file, start_date, end_date))
        return 0
    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        return 1


def mask_connection_url(url: str) -> str:
    """Mask password in connection URL for logging."""
    try:
        from scp_shared.common.security import mask_connection_url as mask_url

        return mask_url(url)
    except ImportError:
        # Fallback if shared library not available
        if "@" in url:
            parts = url.split("@")
            if "://" in parts[0]:
                protocol_user = parts[0].split("://")
                if len(protocol_user) == 2:
                    protocol = protocol_user[0]
                    user_pass = protocol_user[1]
                    if ":" in user_pass:
                        user = user_pass.split(":")[0]
                        return f"{protocol}://{user}:***@{parts[1]}"
        return url


if __name__ == "__main__":
    sys.exit(main())

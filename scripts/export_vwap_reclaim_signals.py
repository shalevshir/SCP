#!/usr/bin/env python3
"""Export VWAP_RECLAIM signals with Watch or A+ confidence to JSON.

This script queries the signal_history table for VWAP_RECLAIM signals
that were classified as 'Watch' or 'A+' confidence and exports all
data to a JSON file for analysis.

Usage:
    python scripts/export_vwap_reclaim_signals.py [--output OUTPUT_FILE]
    python scripts/export_vwap_reclaim_signals.py --start 2024-01-01 --end 2024-12-31

Example:
    python scripts/export_vwap_reclaim_signals.py -o vwap_signals.json
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "services" / "shared" / "src"))


async def get_db_connection() -> asyncpg.Connection:
    """Create database connection from environment variables."""
    database_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://scp:scp_dev_password@localhost:5432/scp",
    )
    return await asyncpg.connect(database_url)


async def export_vwap_reclaim_signals(
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[dict[str, Any]]:
    """Query VWAP_RECLAIM signals with Watch or A+ confidence.

    Args:
        start: Optional start timestamp filter
        end: Optional end timestamp filter

    Returns:
        List of signal records with all columns
    """
    conn = await get_db_connection()

    try:
        # Build query with optional time filters
        conditions = [
            "setup_type = 'VWAP_RECLAIM'",
            "confidence IN ('A+', 'Watch')",
        ]
        params: list[Any] = []
        param_idx = 1

        if start is not None:
            conditions.append(f"timestamp >= ${param_idx}")
            params.append(start)
            param_idx += 1

        if end is not None:
            conditions.append(f"timestamp < ${param_idx}")
            params.append(end)
            param_idx += 1

        query = f"""
            SELECT
                id,
                timestamp,
                symbol,
                timeframe,
                direction,
                setup_type,
                score,
                confidence,
                was_approved,
                rejection_stage,
                features_snapshot,
                htf_bias_snapshot,
                factor_scores,
                diagnostics,
                signal_message_id,
                trade_id,
                created_at
            FROM signal_history
            WHERE {' AND '.join(conditions)}
            ORDER BY timestamp ASC
        """

        rows = await conn.fetch(query, *params)

        signals = []
        for row in rows:
            # Parse JSONB fields
            features_snapshot = row["features_snapshot"]
            htf_bias_snapshot = row["htf_bias_snapshot"]
            factor_scores = row["factor_scores"]
            diagnostics = row["diagnostics"]

            # Handle both string and dict types (asyncpg may auto-parse JSONB)
            if isinstance(features_snapshot, str):
                features_snapshot = json.loads(features_snapshot)
            if isinstance(htf_bias_snapshot, str):
                htf_bias_snapshot = json.loads(htf_bias_snapshot)
            if isinstance(factor_scores, str):
                factor_scores = json.loads(factor_scores)
            if isinstance(diagnostics, str):
                diagnostics = json.loads(diagnostics)

            signal_dict = {
                "id": str(row["id"]),
                "timestamp": row["timestamp"].isoformat(),
                "symbol": row["symbol"],
                "timeframe": row["timeframe"],
                "direction": row["direction"],
                "setup_type": row["setup_type"],
                "score": float(row["score"]),
                "confidence": row["confidence"],
                "was_approved": row["was_approved"],
                "rejection_stage": row["rejection_stage"],
                "features_snapshot": features_snapshot,
                "htf_bias_snapshot": htf_bias_snapshot,
                "factor_scores": factor_scores,
                "diagnostics": diagnostics,
                "signal_message_id": (
                    str(row["signal_message_id"]) if row["signal_message_id"] else None
                ),
                "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
                "created_at": row["created_at"].isoformat(),
            }
            signals.append(signal_dict)

        return signals

    finally:
        await conn.close()


def parse_date(date_str: str) -> datetime:
    """Parse date string to datetime with UTC timezone."""
    dt = datetime.fromisoformat(date_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Export VWAP_RECLAIM signals with Watch or A+ confidence to JSON"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="vwap_reclaim_signals.json",
        help="Output JSON file path (default: vwap_reclaim_signals.json)",
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date filter (ISO format, e.g., 2024-01-01)",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date filter (ISO format, e.g., 2024-12-31)",
    )

    args = parser.parse_args()

    # Parse date filters
    start = parse_date(args.start) if args.start else None
    end = parse_date(args.end) if args.end else None

    print(f"Exporting VWAP_RECLAIM signals (confidence: A+ or Watch)...")
    if start:
        print(f"  Start: {start.isoformat()}")
    if end:
        print(f"  End: {end.isoformat()}")

    # Query signals
    signals = await export_vwap_reclaim_signals(start=start, end=end)

    # Summary stats
    a_plus_count = sum(1 for s in signals if s["confidence"] == "A+")
    watch_count = sum(1 for s in signals if s["confidence"] == "Watch")
    approved_count = sum(1 for s in signals if s["was_approved"])

    print(f"\nFound {len(signals)} signals:")
    print(f"  A+ confidence: {a_plus_count}")
    print(f"  Watch confidence: {watch_count}")
    print(f"  Approved (published): {approved_count}")

    # Write to JSON file
    output_path = Path(args.output)
    with output_path.open("w") as f:
        json.dump(
            {
                "export_timestamp": datetime.now(timezone.utc).isoformat(),
                "filters": {
                    "setup_type": "VWAP_RECLAIM",
                    "confidence": ["A+", "Watch"],
                    "start": start.isoformat() if start else None,
                    "end": end.isoformat() if end else None,
                },
                "summary": {
                    "total_signals": len(signals),
                    "a_plus_count": a_plus_count,
                    "watch_count": watch_count,
                    "approved_count": approved_count,
                },
                "signals": signals,
            },
            f,
            indent=2,
            default=str,
        )

    print(f"\nExported to: {output_path.absolute()}")


if __name__ == "__main__":
    asyncio.run(main())

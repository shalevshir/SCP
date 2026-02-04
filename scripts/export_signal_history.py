#!/usr/bin/env python3
"""Export signal_history data for comparison and verification.

This script exports all signals from the signal_history table to a JSON file
for later comparison after optimization changes.

Usage:
    python scripts/export_signal_history.py --output signals_before_optimization.json
"""

import argparse
import asyncio
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from scp_shared.common import get_logger
from scp_shared.database import DatabasePool

logger = get_logger(__name__)


async def export_signal_history(
    database_url: str,
    output_file: Path,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> None:
    """Export signal_history data to JSON file.

    Args:
        database_url: PostgreSQL connection URL
        output_file: Path to output JSON file
        start_date: Optional start date filter
        end_date: Optional end date filter
    """
    db_pool = DatabasePool(database_url)
    await db_pool.connect()

    try:
        # Build query with optional date filters
        query = """
            SELECT
                id,
                timestamp,
                symbol,
                timeframe,
                setup_type,
                direction,
                score,
                confidence,
                was_approved,
                rejection_stage,
                signal_message_id,
                trade_id,
                created_at
            FROM signal_history
        """

        conditions = []
        params = []

        if start_date:
            conditions.append(f"timestamp >= ${len(params) + 1}")
            params.append(start_date)

        if end_date:
            conditions.append(f"timestamp <= ${len(params) + 1}")
            params.append(end_date)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp, id"

        logger.info(f"Fetching signal_history records...")
        rows = await db_pool.fetch(query, *params)

        # Convert to JSON-serializable format
        signals = []
        for row in rows:
            signal = dict(row)
            # Convert datetime, UUID, and Decimal objects to JSON-compatible types
            for key, value in signal.items():
                if isinstance(value, datetime):
                    signal[key] = value.isoformat()
                elif isinstance(value, Decimal):
                    signal[key] = float(value)
                elif value is not None and hasattr(value, "hex"):  # UUID
                    signal[key] = str(value)
            signals.append(signal)

        # Write to file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(
                {
                    "exported_at": datetime.now().isoformat(),
                    "total_signals": len(signals),
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None,
                    "signals": signals,
                },
                f,
                indent=2,
            )

        logger.info(f"✓ Exported {len(signals)} signals to {output_file}")

        # Print summary
        approved = sum(1 for s in signals if s["was_approved"])
        rejected = len(signals) - approved
        logger.info(f"  Approved: {approved}")
        logger.info(f"  Rejected: {rejected}")

        # Breakdown by rejection stage
        if rejected > 0:
            rejection_counts: dict[str, int] = {}
            for s in signals:
                if not s["was_approved"] and s["rejection_stage"]:
                    rejection_counts[s["rejection_stage"]] = (
                        rejection_counts.get(s["rejection_stage"], 0) + 1
                    )
            logger.info("  Rejection breakdown:")
            for stage, count in sorted(rejection_counts.items()):
                logger.info(f"    {stage}: {count}")

    finally:
        await db_pool.close()


async def compare_signal_histories(
    file1: Path,
    file2: Path,
) -> None:
    """Compare two signal_history exports and report differences.

    Args:
        file1: Path to first export file
        file2: Path to second export file
    """
    with open(file1) as f:
        data1 = json.load(f)
    with open(file2) as f:
        data2 = json.load(f)

    signals1 = data1["signals"]
    signals2 = data2["signals"]

    logger.info(f"\nComparing signal exports:")
    logger.info(f"  File 1: {file1} ({len(signals1)} signals)")
    logger.info(f"  File 2: {file2} ({len(signals2)} signals)")

    # Compare counts
    if len(signals1) != len(signals2):
        logger.error(f"  ❌ Different signal counts: {len(signals1)} vs {len(signals2)}")
        return

    # Compare each signal (excluding id and created_at which may differ)
    compare_fields = [
        "timestamp",
        "symbol",
        "timeframe",
        "setup_type",
        "direction",
        "score",
        "confidence",
        "was_approved",
        "rejection_stage",
        "signal_message_id",
        "trade_id",
    ]

    differences = []
    for i, (s1, s2) in enumerate(zip(signals1, signals2)):
        for field in compare_fields:
            if s1.get(field) != s2.get(field):
                differences.append(
                    {
                        "index": i,
                        "timestamp": s1["timestamp"],
                        "field": field,
                        "value1": s1.get(field),
                        "value2": s2.get(field),
                    }
                )

    if differences:
        logger.error(f"  ❌ Found {len(differences)} differences:")
        for diff in differences[:10]:  # Show first 10
            logger.error(
                f"    Signal {diff['index']} ({diff['timestamp']}): "
                f"{diff['field']} = {diff['value1']} vs {diff['value2']}"
            )
        if len(differences) > 10:
            logger.error(f"    ... and {len(differences) - 10} more")
    else:
        logger.info("  ✓ Signal histories are identical!")


async def main():
    parser = argparse.ArgumentParser(description="Export signal_history data")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/signals_export.json"),
        help="Output JSON file path",
    )
    parser.add_argument(
        "--database-url",
        default="postgresql://scp:scp_dev_password@localhost:5432/scp",
        help="Database connection URL",
    )
    parser.add_argument(
        "--start",
        type=lambda s: datetime.fromisoformat(s),
        help="Start date (ISO format)",
    )
    parser.add_argument(
        "--end",
        type=lambda s: datetime.fromisoformat(s),
        help="End date (ISO format)",
    )
    parser.add_argument(
        "--compare",
        nargs=2,
        type=Path,
        metavar=("FILE1", "FILE2"),
        help="Compare two export files",
    )

    args = parser.parse_args()

    if args.compare:
        await compare_signal_histories(args.compare[0], args.compare[1])
    else:
        await export_signal_history(
            args.database_url,
            args.output,
            args.start,
            args.end,
        )


if __name__ == "__main__":
    asyncio.run(main())

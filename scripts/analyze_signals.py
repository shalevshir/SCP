#!/usr/bin/env python3
"""Signal history analysis and export tool.

This script provides utilities for analyzing and exporting signal history
from the signal_history table, enabling post-hoc analysis of signal decisions,
rejection patterns, and debugging of backtests and live/paper trading.

Usage:
    # Export all signals for a date range
    python scripts/analyze_signals.py export \
        --start 2025-11-03 \
        --end 2025-11-08 \
        --output signals_export.json

    # Export only rejected signals
    python scripts/analyze_signals.py export \
        --start 2025-11-03 \
        --end 2025-11-08 \
        --rejected-only \
        --output rejected_signals.json

    # Analyze rejection patterns
    python scripts/analyze_signals.py analyze \
        --start 2025-11-03 \
        --end 2025-11-08

    # Export specific setup type
    python scripts/analyze_signals.py export \
        --start 2025-11-03 \
        --end 2025-11-08 \
        --setup-type VWAP_RECLAIM \
        --output vwap_reclaim_signals.csv
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scp_shared.common.logger import get_logger
from scp_shared.database import DatabasePool

logger = get_logger(__name__)


async def export_signal_history(
    db_pool: DatabasePool,
    start: datetime,
    end: datetime,
    output_path: str,
    rejected_only: bool = False,
    approved_only: bool = False,
    setup_type: str | None = None,
    format: str = "json",
) -> None:
    """Export signal history to JSON or CSV file.
    
    Args:
        db_pool: Database connection pool
        start: Start timestamp (inclusive)
        end: End timestamp (exclusive)
        output_path: Output file path
        rejected_only: Only export rejected signals
        approved_only: Only export approved signals
        setup_type: Filter by setup type (None = all)
        format: Output format ("json" or "csv")
    """
    # Build query
    conditions = ["timestamp >= $1", "timestamp < $2"]
    params: list = [start, end]
    param_idx = 3
    
    if rejected_only:
        conditions.append("was_approved = FALSE")
    elif approved_only:
        conditions.append("was_approved = TRUE")
    
    if setup_type is not None:
        conditions.append(f"setup_type = ${param_idx}")
        params.append(setup_type)
        param_idx += 1
    
    query = f"""
        SELECT
            id, timestamp, symbol, timeframe, direction, setup_type,
            score, confidence, was_approved, rejection_stage,
            features_snapshot, htf_bias_snapshot,
            factor_scores, diagnostics,
            signal_message_id, trade_id, created_at
        FROM signal_history
        WHERE {' AND '.join(conditions)}
        ORDER BY timestamp ASC
    """
    
    logger.info(
        f"Querying signal history from {start.isoformat()} "
        f"to {end.isoformat()}"
    )
    rows = await db_pool.fetch(query, *params)
    
    if not rows:
        logger.warning("No signals found for the specified criteria")
        return
    
    logger.info(f"Retrieved {len(rows)} signals")
    
    # Convert to list of dicts
    signals = []
    for row in rows:
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
            "features_snapshot": json.loads(row["features_snapshot"]),
            "htf_bias_snapshot": json.loads(row["htf_bias_snapshot"]),
            "factor_scores": json.loads(row["factor_scores"]),
            "diagnostics": json.loads(row["diagnostics"]),
            "signal_message_id": (
                str(row["signal_message_id"]) if row["signal_message_id"] else None
            ),
            "trade_id": str(row["trade_id"]) if row["trade_id"] else None,
            "created_at": row["created_at"].isoformat(),
        }
        signals.append(signal_dict)
    
    # Export based on format
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    if format == "json":
        with open(output_file, "w") as f:
            json.dump(signals, f, indent=2)
        logger.info(f"Exported {len(signals)} signals to {output_path} (JSON)")
    
    elif format == "csv":
        # Flatten nested structures for CSV export
        flattened = []
        for signal in signals:
            flat = {
                "id": signal["id"],
                "timestamp": signal["timestamp"],
                "symbol": signal["symbol"],
                "timeframe": signal["timeframe"],
                "direction": signal["direction"],
                "setup_type": signal["setup_type"],
                "score": signal["score"],
                "confidence": signal["confidence"],
                "was_approved": signal["was_approved"],
                "rejection_stage": signal["rejection_stage"],
                # Key features
                "close": signal["features_snapshot"].get("close"),
                "vwap": signal["features_snapshot"].get("vwap"),
                "rsi": signal["features_snapshot"].get("rsi"),
                "ema_9": signal["features_snapshot"].get("ema_9"),
                "dxy_corr": signal["features_snapshot"].get("dxy_corr"),
                "structure_label": signal["features_snapshot"].get(
                    "structure_label"
                ),
                "bos_age": signal["features_snapshot"].get("bos_age"),
                "structure_clarity": signal["features_snapshot"].get(
                    "structure_clarity"
                ),
                # HTF bias
                "htf_bias": signal["htf_bias_snapshot"].get("bias"),
                "htf_score": signal["htf_bias_snapshot"].get("score"),
                "htf_confidence": signal["htf_bias_snapshot"].get("confidence"),
                "dxy_aligned": signal["htf_bias_snapshot"].get("dxy_aligned"),
                "chop_detected": signal["htf_bias_snapshot"].get("chop_detected"),
                # Diagnostics
                "rejection_passed": signal["diagnostics"].get(
                    "rejection_analysis", {}
                ).get("passed"),
                "primary_rejection_reason": signal["diagnostics"].get(
                    "rejection_analysis", {}
                ).get("primary_rejection_reason"),
                "score_gap": signal["diagnostics"].get(
                    "rejection_analysis", {}
                ).get("score_gap"),
                # IDs
                "signal_message_id": signal["signal_message_id"],
                "trade_id": signal["trade_id"],
            }
            flattened.append(flat)
        
        df = pd.DataFrame(flattened)
        df.to_csv(output_file, index=False)
        logger.info(f"Exported {len(signals)} signals to {output_path} (CSV)")
    
    else:
        raise ValueError(f"Unsupported format: {format}")


async def analyze_rejections(
    db_pool: DatabasePool,
    start: datetime,
    end: datetime,
) -> dict:
    """Analyze rejection patterns for a time period.
    
    Args:
        db_pool: Database connection pool
        start: Start timestamp (inclusive)
        end: End timestamp (exclusive)
        
    Returns:
        Dictionary with rejection analysis
    """
    logger.info(f"Analyzing rejections from {start.isoformat()} to {end.isoformat()}")
    
    # 1. Count total signals
    total_query = """
        SELECT COUNT(*) as total
        FROM signal_history
        WHERE timestamp >= $1 AND timestamp < $2
    """
    total_row = await db_pool.fetchrow(total_query, start, end)
    total_signals = total_row["total"]
    
    # 2. Count approved vs rejected
    approval_query = """
        SELECT was_approved, COUNT(*) as count
        FROM signal_history
        WHERE timestamp >= $1 AND timestamp < $2
        GROUP BY was_approved
    """
    approval_rows = await db_pool.fetch(approval_query, start, end)
    approval_counts = {row["was_approved"]: row["count"] for row in approval_rows}
    
    approved_count = approval_counts.get(True, 0)
    rejected_count = approval_counts.get(False, 0)
    
    # 3. Rejection reasons breakdown
    rejection_query = """
        SELECT rejection_stage, COUNT(*) as count
        FROM signal_history
        WHERE timestamp >= $1
          AND timestamp < $2
          AND was_approved = FALSE
        GROUP BY rejection_stage
        ORDER BY count DESC
    """
    rejection_rows = await db_pool.fetch(rejection_query, start, end)
    rejection_breakdown = {
        row["rejection_stage"]: row["count"] for row in rejection_rows
    }
    
    # 4. Setup type distribution (rejected signals only)
    setup_query = """
        SELECT setup_type, COUNT(*) as count
        FROM signal_history
        WHERE timestamp >= $1
          AND timestamp < $2
          AND was_approved = FALSE
        GROUP BY setup_type
        ORDER BY count DESC
    """
    setup_rows = await db_pool.fetch(setup_query, start, end)
    rejected_by_setup = {row["setup_type"]: row["count"] for row in setup_rows}
    
    # 5. Score distribution for rejected signals
    score_query = """
        SELECT
            FLOOR(score) as score_bucket,
            COUNT(*) as count
        FROM signal_history
        WHERE timestamp >= $1
          AND timestamp < $2
          AND was_approved = FALSE
        GROUP BY FLOOR(score)
        ORDER BY score_bucket
    """
    score_rows = await db_pool.fetch(score_query, start, end)
    score_distribution = {int(row["score_bucket"]): row["count"] for row in score_rows}
    
    # 6. Near-miss signals (score >= 7.0 but rejected)
    near_miss_query = """
        SELECT COUNT(*) as count
        FROM signal_history
        WHERE timestamp >= $1
          AND timestamp < $2
          AND was_approved = FALSE
          AND score >= 7.0
    """
    near_miss_row = await db_pool.fetchrow(near_miss_query, start, end)
    near_miss_count = near_miss_row["count"]
    
    # Calculate approval rate
    approval_rate_pct = (
        approved_count / total_signals * 100 if total_signals > 0 else 0
    )
    
    analysis = {
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
        "summary": {
            "total_signals": total_signals,
            "approved": approved_count,
            "rejected": rejected_count,
            "approval_rate": f"{approval_rate_pct:.1f}%",
        },
        "rejection_breakdown": rejection_breakdown,
        "rejected_by_setup": rejected_by_setup,
        "score_distribution": score_distribution,
        "near_miss_signals": near_miss_count,
    }
    
    # Print analysis
    print("\n" + "="*80)
    print("SIGNAL REJECTION ANALYSIS")
    print("="*80)
    print(f"\nPeriod: {start.date()} to {end.date()}")
    print(f"\nTotal Signals: {total_signals}")
    approval_pct = (
        approved_count / total_signals * 100 if total_signals > 0 else 0
    )
    rejection_pct = (
        rejected_count / total_signals * 100 if total_signals > 0 else 0
    )
    print(f"  Approved (A+): {approved_count} ({approval_pct:.1f}%)")
    print(f"  Rejected: {rejected_count} ({rejection_pct:.1f}%)")
    
    print("\nRejection Reasons:")
    for reason, count in sorted(
        rejection_breakdown.items(), key=lambda x: x[1], reverse=True
    ):
        pct = count / rejected_count * 100 if rejected_count > 0 else 0
        print(f"  {reason}: {count} ({pct:.1f}%)")
    
    print("\nRejected Signals by Setup Type:")
    for setup, count in sorted(
        rejected_by_setup.items(), key=lambda x: x[1], reverse=True
    ):
        pct = count / rejected_count * 100 if rejected_count > 0 else 0
        print(f"  {setup}: {count} ({pct:.1f}%)")
    
    print("\nScore Distribution (Rejected Signals):")
    for score, count in sorted(score_distribution.items()):
        print(f"  {score}-{score+1}: {count}")
    
    print(f"\nNear-Miss Signals (score >= 7.0): {near_miss_count}")
    print("="*80 + "\n")
    
    return analysis


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze and export signal history")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Export command
    export_parser = subparsers.add_parser("export", help="Export signal history")
    export_parser.add_argument(
        "--start", required=True, help="Start date (YYYY-MM-DD)"
    )
    export_parser.add_argument(
        "--end", required=True, help="End date (YYYY-MM-DD)"
    )
    export_parser.add_argument(
        "--output", required=True, help="Output file path"
    )
    export_parser.add_argument(
        "--rejected-only",
        action="store_true",
        help="Only export rejected signals",
    )
    export_parser.add_argument(
        "--approved-only",
        action="store_true",
        help="Only export approved signals",
    )
    export_parser.add_argument(
        "--setup-type", help="Filter by setup type (e.g., VWAP_RECLAIM)"
    )
    export_parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        help="Output format",
    )
    
    # Analyze command
    analyze_parser = subparsers.add_parser(
        "analyze", help="Analyze rejection patterns"
    )
    analyze_parser.add_argument(
        "--start", required=True, help="Start date (YYYY-MM-DD)"
    )
    analyze_parser.add_argument(
        "--end", required=True, help="End date (YYYY-MM-DD)"
    )
    analyze_parser.add_argument(
        "--output", help="Output JSON file for analysis results (optional)"
    )
    
    args = parser.parse_args()
    
    # Parse dates
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)
    
    # Connect to database
    import os
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://scp:scp_dev_password@localhost:5432/scp"
    )
    db_pool = DatabasePool(database_url)
    await db_pool.connect()
    
    try:
        if args.command == "export":
            await export_signal_history(
                db_pool=db_pool,
                start=start,
                end=end,
                output_path=args.output,
                rejected_only=args.rejected_only,
                approved_only=args.approved_only,
                setup_type=args.setup_type,
                format=args.format,
            )
        
        elif args.command == "analyze":
            analysis = await analyze_rejections(
                db_pool=db_pool,
                start=start,
                end=end,
            )
            
            # Optionally save analysis to JSON
            if args.output:
                output_file = Path(args.output)
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with open(output_file, "w") as f:
                    json.dump(analysis, f, indent=2)
                logger.info(f"Saved analysis to {args.output}")
    
    finally:
        await db_pool.close()


if __name__ == "__main__":
    asyncio.run(main())

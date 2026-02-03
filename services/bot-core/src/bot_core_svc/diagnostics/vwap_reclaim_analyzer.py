"""VWAP_RECLAIM constraint failure analyzer.

This tool queries the signal_history table to identify which constraints
are causing VWAP_RECLAIM setups to be rejected. It aggregates failures
by constraint name and provides example context values for debugging.

Usage:
    # Run as module
    python -m bot_core_svc.diagnostics.vwap_reclaim_analyzer \\
        --start "2025-01-15" --end "2025-01-20"

    # Run directly
    python vwap_reclaim_analyzer.py --days 7
"""

import argparse
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from scp_shared.common.logger import get_logger
from scp_shared.database import DatabasePool

logger = get_logger(__name__)


async def analyze_vwap_reclaim_rejections(
    start: datetime,
    end: datetime,
    db_pool: DatabasePool,
) -> dict:
    """Analyze VWAP_RECLAIM constraint failures from signal_history.

    Args:
        start: Start timestamp (inclusive)
        end: End timestamp (exclusive)
        db_pool: Database connection pool

    Returns:
        Dictionary with analysis results:
        - total_rejected: Total rejected signals
        - with_vwap_diagnostics: Signals with VWAP_RECLAIM validation data
        - top_constraints: List of (constraint_name, count, example_context)
    """
    # Query 1: Get total rejected signals
    total_query = """
        SELECT COUNT(*) as total
        FROM signal_history
        WHERE timestamp >= $1 AND timestamp < $2
          AND setup_type = 'REJECTED'
    """

    total_row = await db_pool.fetchrow(total_query, start, end)
    total_rejected = total_row["total"] if total_row else 0

    # Query 2: Get VWAP_RECLAIM constraint failures grouped by constraint
    constraint_query = """
        WITH grouped_failures AS (
            SELECT
                diagnostics->'vwap_reclaim_validation'->>'failed_constraint' as constraint_name,
                diagnostics->'vwap_reclaim_validation'->>'reject_reason' as reject_reason,
                COUNT(*) as failure_count
            FROM signal_history
            WHERE timestamp >= $1 AND timestamp < $2
              AND setup_type = 'REJECTED'
              AND diagnostics ? 'vwap_reclaim_validation'
            GROUP BY constraint_name, reject_reason
        ),
        examples AS (
            SELECT DISTINCT ON (diagnostics->'vwap_reclaim_validation'->>'failed_constraint')
                diagnostics->'vwap_reclaim_validation'->>'failed_constraint' as constraint_name,
                diagnostics->'vwap_reclaim_validation'->'context_snapshot' as example_context
            FROM signal_history
            WHERE timestamp >= $1 AND timestamp < $2
              AND setup_type = 'REJECTED'
              AND diagnostics ? 'vwap_reclaim_validation'
        )
        SELECT
            gf.constraint_name,
            gf.reject_reason,
            gf.failure_count,
            ex.example_context
        FROM grouped_failures gf
        LEFT JOIN examples ex ON gf.constraint_name = ex.constraint_name
        ORDER BY gf.failure_count DESC
        LIMIT 20
    """

    constraint_rows = await db_pool.fetch(constraint_query, start, end)

    # Parse results
    top_constraints = []
    for row in constraint_rows:
        constraint_name = row["constraint_name"]
        reject_reason = row["reject_reason"]
        failure_count = row["failure_count"]
        example_context = json.loads(row["example_context"]) if row["example_context"] else {}

        top_constraints.append(
            {
                "constraint": constraint_name,
                "reason": reject_reason,
                "count": failure_count,
                "example": example_context,
            }
        )

    with_diagnostics = sum(item["count"] for item in top_constraints)

    return {
        "total_rejected": total_rejected,
        "with_vwap_diagnostics": with_diagnostics,
        "without_diagnostics": total_rejected - with_diagnostics,
        "top_constraints": top_constraints,
    }


def format_analysis_report(results: dict, start: datetime, end: datetime) -> str:
    """Format analysis results as human-readable report.

    Args:
        results: Analysis results from analyze_vwap_reclaim_rejections()
        start: Start timestamp
        end: End timestamp

    Returns:
        Formatted report string
    """
    lines = []
    lines.append("=" * 80)
    lines.append("VWAP_RECLAIM Constraint Failure Analysis")
    lines.append("=" * 80)
    lines.append(f"Period: {start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    lines.append(f"Total REJECTED signals: {results['total_rejected']}")
    lines.append(f"  - With VWAP_RECLAIM diagnostics: {results['with_vwap_diagnostics']}")
    lines.append(f"  - Without diagnostics: {results['without_diagnostics']}")
    lines.append("")

    if not results["top_constraints"]:
        lines.append("No VWAP_RECLAIM constraint failures found.")
        lines.append("")
        lines.append("Possible reasons:")
        lines.append("  1. Enhanced diagnostics not deployed yet (code change needed)")
        lines.append("  2. No VWAP_RECLAIM attempts in this period")
        lines.append("  3. All VWAP_RECLAIM setups passing (unlikely if always rejected)")
    else:
        lines.append("Top Failing Constraints:")
        lines.append("-" * 80)
        lines.append("")

        for idx, item in enumerate(results["top_constraints"], 1):
            constraint = item["constraint"]
            reason = item["reason"]
            count = item["count"]
            example = item["example"]

            lines.append(f"{idx}. Constraint: {constraint}")
            lines.append(f"   Failures: {count}")
            lines.append(f"   Reason: {reason}")
            lines.append(f"   Example context: {json.dumps(example, indent=6)}")
            lines.append("")

    lines.append("=" * 80)
    lines.append("")
    lines.append("Next Steps:")
    lines.append("  1. Review top failing constraint(s)")
    lines.append("  2. Check if constraint threshold is too strict")
    lines.append("  3. Verify feature values are calculated correctly")
    lines.append("  4. Adjust constraint in config/setups.yaml or fix data pipeline")
    lines.append("  5. Re-run analysis after changes to verify improvement")
    lines.append("")

    return "\n".join(lines)


async def main():
    """CLI entry point for VWAP_RECLAIM constraint analyzer."""
    parser = argparse.ArgumentParser(
        description="Analyze VWAP_RECLAIM constraint failures from signal_history"
    )
    parser.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD or YYYY-MM-DD HH:MM)",
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD or YYYY-MM-DD HH:MM)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to analyze (default: 7, used if --start/--end not provided)",
    )
    parser.add_argument(
        "--db-dsn",
        type=str,
        default="postgresql://scp_user@localhost:5432/scp_trading",
        help="Database DSN (default: postgresql://scp_user@localhost:5432/scp_trading)",
    )

    args = parser.parse_args()

    # Parse date range
    if args.start and args.end:
        start = datetime.fromisoformat(args.start)
        end = datetime.fromisoformat(args.end)
    else:
        end = datetime.now()
        start = end - timedelta(days=args.days)

    logger.info(f"Analyzing VWAP_RECLAIM rejections from {start} to {end}")

    # Connect to database
    db_pool = DatabasePool(
        dsn=args.db_dsn,
        min_size=1,
        max_size=2,
    )

    try:
        await db_pool.connect()

        # Run analysis
        results = await analyze_vwap_reclaim_rejections(start, end, db_pool)

        # Format and print report
        report = format_analysis_report(results, start, end)
        print(report)

        # Save report to file
        report_dir = Path("diagnostics_reports")
        report_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"vwap_reclaim_analysis_{timestamp}.txt"

        with open(report_file, "w") as f:
            f.write(report)

        logger.info(f"Report saved to: {report_file}")

    finally:
        await db_pool.close()


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Full validation workflow: Backtester vs Databento Replay.

This script runs a complete validation cycle:
1. Run backtester on date range (to get expected results)
2. Fetch and replay data from Databento through microservices
3. Compare trade outcomes (signals, entries, exits, P&L)
4. Generate detailed comparison report

This validates that the microservices produce correct results when using
real Databento data (vs CSV data used in standard replay).

Usage:
    export DATABENTO_API_KEY="db-your-key"
    python scripts/validate_databento_replay.py \\
        --start 2024-11-05 \\
        --end 2024-11-12 \\
        --speed 0
"""

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtester.results_io import load_results
from scripts.collect_microservice_trades import collect_trades
from scripts.compare_results import compare_backtest_vs_microservices
from scripts.replay_databento_historical import (
    DatabentoHistoricalReplay,
    replay_candles,
)
from scp_shared.common import get_logger

logger = get_logger(__name__)


async def main():
    """Main validation workflow."""
    parser = argparse.ArgumentParser(
        description="Validate microservices using Databento historical data"
    )

    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--api-key",
        required=True,
        help="Databento API key (or set DATABENTO_API_KEY env var)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=0,
        help="Replay speed (0=turbo, default: 0)",
    )
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379",
        help="Redis URL (default: redis://localhost:6379)",
    )
    parser.add_argument(
        "--database-url",
        default="postgresql://scp:scp_dev_password@localhost:5432/scp",
        help="Database URL",
    )
    parser.add_argument(
        "--output-dir",
        default="output/databento_validation",
        help="Output directory for reports",
    )

    args = parser.parse_args()

    # Parse dates
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 80)
    logger.info("Databento Historical Replay Validation")
    logger.info("=" * 80)
    logger.info(f"Date range: {args.start} to {args.end}")
    logger.info(f"Speed: {args.speed}x")
    logger.info(f"Output: {output_dir}")
    logger.info("=" * 80)

    # Step 1: Run backtester
    logger.info("\n[1/4] Running backtester...")
    backtest_file = output_dir / f"backtest_{args.start}_{args.end}.json"

    result = subprocess.run(
        [
            "poetry",
            "run",
            "python",
            "scripts/run_backtest_and_view.py",
            "--start",
            start.isoformat(),
            "--end",
            end.isoformat(),
            "--no-view",
            "--output-file",
            str(backtest_file),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"Backtester failed:\n{result.stderr}")
        return 1

    backtest_results = load_results(backtest_file)
    logger.info(f"✓ Backtester complete: {backtest_results.total_trades} trades")

    # Step 2: Clean Redis and database
    logger.info("\n[2/4] Cleaning environment...")
    subprocess.run(["docker", "exec", "scp-redis", "redis-cli", "FLUSHDB"], check=False)
    subprocess.run(
        [
            "docker",
            "exec",
            "scp-postgres",
            "psql",
            "-U",
            "scp",
            "-d",
            "scp",
            "-c",
            "TRUNCATE TABLE trades CASCADE",
        ],
        check=False,
    )
    logger.info("✓ Environment cleaned")

    # Step 3: Replay from Databento
    logger.info("\n[3/4] Fetching and replaying data from Databento...")

    replay = DatabentoHistoricalReplay(api_key=args.api_key)

    # Fetch historical data
    candles_gc = replay.fetch_historical_data("GC", start, end)
    candles_dxy = replay.fetch_historical_data("DXY", start, end)

    if not candles_gc:
        logger.error("Failed to fetch GC data from Databento")
        return 1

    # Replay through pipeline
    replay_stats = await replay_candles(
        candles_gc=candles_gc,
        candles_dxy=candles_dxy,
        redis_url=args.redis_url,
        speed_multiplier=args.speed,
        processing_delay=10.0,
    )

    logger.info(f"✓ Replay complete: {replay_stats['candles_published']} candles")

    # Step 4: Compare results
    logger.info("\n[4/4] Comparing results...")

    microservice_trades = await collect_trades(
        database_url=args.database_url,
        start=start,
        end=end,
    )

    logger.info(f"Microservices trades: {len(microservice_trades)}")

    # Convert backtester trades to dict format
    from backtester.trade import to_dict

    backtest_trades = [to_dict(trade) for trade in backtest_results.trades]

    # Compare
    report = compare_backtest_vs_microservices(backtest_trades, microservice_trades)

    # Print summary
    report.print_summary()

    # Save detailed report
    report_file = output_dir / f"comparison_report_{args.start}_{args.end}.json"
    with open(report_file, "w") as f:
        json.dump(
            {
                "generated_at": datetime.now().isoformat(),
                "source": "databento",
                "date_range": {"start": args.start, "end": args.end},
                "report": report.to_dict(),
            },
            f,
            indent=2,
        )

    logger.info(f"\n✓ Detailed report saved to {report_file}")

    # Final assessment
    logger.info("\n" + "=" * 80)
    if report.backtest_count > 0:
        match_pct = report.match_rate if hasattr(report, "match_rate") else 0
        if match_pct >= 90.0:
            logger.info("✅ VALIDATION PASSED")
            logger.info(f"Match rate: {match_pct:.1f}%")
            return 0
        else:
            logger.warning(f"⚠️  VALIDATION PARTIAL: {match_pct:.1f}% match rate")
            return 1
    else:
        logger.warning("⚠️  No trades generated (may be normal for this date range)")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

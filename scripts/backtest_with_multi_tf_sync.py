#!/usr/bin/env python3
"""Example script demonstrating Multi-Timeframe Sync Layer integration with backtesting.

This script shows how to use the new multi-timeframe sync layer for efficient
HTF bias computation in backtesting.

Usage:
    poetry run python scripts/backtest_with_multi_tf_sync.py \
        --data-dir data/gc_dx_ohlcv \
        --start 2025-07-01T10:00:00Z \
        --end 2025-07-01T13:00:00Z \
        --htf-approach streaming
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from backtester.pipeline import (
    run_backtest_with_entries_multi_tf,
    run_backtest_with_trades_multi_tf,
)
from common.logger import get_logger
from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer

logger = get_logger(__name__)


def parse_iso_datetime(value: str) -> datetime:
    """Parse ISO-8601 datetime strings, defaulting to UTC when tzinfo missing."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Backtest with Multi-Timeframe Sync Layer integration"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/gc_dx_ohlcv"),
        help="Directory containing GC/DX CSV files (default: data/gc_dx_ohlcv)",
    )
    parser.add_argument(
        "--start",
        type=parse_iso_datetime,
        default=datetime(2025, 7, 1, 10, 0, 0, tzinfo=UTC),
        help="Start datetime (ISO-8601, default: 2025-07-01T10:00:00Z)",
    )
    parser.add_argument(
        "--end",
        type=parse_iso_datetime,
        default=datetime(2025, 7, 1, 13, 0, 0, tzinfo=UTC),
        help="End datetime (ISO-8601, default: 2025-07-01T13:00:00Z)",
    )
    parser.add_argument(
        "--htf-approach",
        type=str,
        choices=["streaming", "vectorized"],
        default="streaming",
        help="HTF feature computation approach (default: streaming)",
    )
    parser.add_argument(
        "--with-trades",
        action="store_true",
        help="Run complete backtest with trade simulation",
    )
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
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory for results (default: output/)",
    )
    return parser


def main() -> None:
    """Main entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 80)
    logger.info("Multi-Timeframe Sync Layer Backtest Example")
    logger.info("=" * 80)
    logger.info(f"Data directory: {args.data_dir}")
    logger.info(f"Date range: {args.start} to {args.end}")
    logger.info(f"HTF approach: {args.htf_approach}")
    logger.info(f"Buffer phase: {args.buffer_phase}")
    logger.info(f"Tier active: {args.tier_active}")

    # Validate data directory
    if not args.data_dir.exists():
        logger.error(f"Data directory not found: {args.data_dir}")
        sys.exit(1)

    # Step 1: Load multi-timeframe data using sync layer
    logger.info("\n" + "=" * 80)
    logger.info("Step 1: Loading multi-timeframe data")
    logger.info("=" * 80)

    try:
        sync_layer = MultiTimeframeSyncLayer(str(args.data_dir))
        multi_tf_data = sync_layer.load(args.start, args.end)

        logger.info(
            f"Loaded {len(multi_tf_data)} synchronized bars "
            f"from {multi_tf_data.execution_timestamps[0]} "
            f"to {multi_tf_data.execution_timestamps[-1]}"
        )
        logger.info(f"Execution timeframe: {multi_tf_data.execution_timeframe}")
        logger.info(f"HTF timeframes: {multi_tf_data.htf_timeframes}")
    except Exception as e:
        logger.error(f"Failed to load multi-timeframe data: {e}", exc_info=True)
        sys.exit(1)

    # Step 2: Define market state
    market_state = {
        "buffer_phase": args.buffer_phase,
        "tier_active": args.tier_active,
        "ceo_directive_active": True,
        "news_ok": True,
        "session_ok": True,
    }

    # Step 3: Run backtest
    logger.info("\n" + "=" * 80)
    logger.info("Step 2: Running backtest pipeline")
    logger.info("=" * 80)

    try:
        if args.with_trades:
            # Run with trade simulation
            risk_config = {
                "risk_per_trade": 350.0 if args.buffer_phase == "startup" else 600.0,
                "buffer_phase": args.buffer_phase,
                "max_contracts": 1,
            }

            trades = run_backtest_with_trades_multi_tf(
                multi_tf_data=multi_tf_data,
                timeframe="1m",
                market_state=market_state,
                risk_config=risk_config,
                htf_approach=args.htf_approach,
                log_signals=True,
                log_dir=str(args.output_dir / "signals"),
            )

            # Analyze results
            logger.info("\n" + "=" * 80)
            logger.info("Step 3: Trade Results")
            logger.info("=" * 80)
            logger.info(f"Total trades: {len(trades)}")

            if trades:
                winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
                losing_trades = [t for t in trades if t.pnl and t.pnl < 0]
                win_rate = len(winning_trades) / len(trades) * 100 if trades else 0

                total_pnl = sum(t.pnl for t in trades if t.pnl)
                total_r = sum(t.r_realized for t in trades if t.r_realized)

                logger.info(f"Winning trades: {len(winning_trades)}")
                logger.info(f"Losing trades: {len(losing_trades)}")
                logger.info(f"Win rate: {win_rate:.1f}%")
                logger.info(f"Total PnL: {total_pnl:.2f} points")
                logger.info(f"Total R: {total_r:.2f}R")

                if total_pnl:
                    logger.info(f"Average R per trade: {total_r / len(trades):.2f}R")
        else:
            # Run with entries only
            executions, processor = run_backtest_with_entries_multi_tf(
                multi_tf_data=multi_tf_data,
                timeframe="1m",
                market_state=market_state,
                htf_approach=args.htf_approach,
                log_signals=True,
                log_dir=str(args.output_dir / "signals"),
            )

            # Analyze results
            logger.info("\n" + "=" * 80)
            logger.info("Step 3: Entry Execution Results")
            logger.info("=" * 80)
            logger.info(f"Total signals: {len(executions)}")

            if executions:
                executed = [e for e in executions if e.executed]
                rejected = [e for e in executions if not e.executed]

                logger.info(f"Executed entries: {len(executed)}")
                logger.info(f"Rejected entries: {len(rejected)}")
                logger.info(
                    f"Execution rate: {len(executed) / len(executions) * 100:.1f}%"
                )

                # Rejection reasons
                if rejected:
                    rejection_reasons = {}
                    for e in rejected:
                        reason = e.rejection_reason or "Unknown"
                        rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1

                    logger.info("\nRejection reasons:")
                    for reason, count in sorted(
                        rejection_reasons.items(), key=lambda x: -x[1]
                    ):
                        logger.info(f"  {reason}: {count}")

        logger.info("\n" + "=" * 80)
        logger.info("Backtest complete!")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

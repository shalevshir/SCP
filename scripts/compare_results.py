#!/usr/bin/env python3
"""Compare backtester results with microservices results.

This script performs trade-by-trade comparison between backtester and microservices,
identifying matches, mismatches, and missing trades. Uses relaxed matching criteria
to account for expected differences in streaming vs batch processing.

Usage:
    # Compare using backtest JSON and database query
    poetry run python scripts/compare_results.py \
        --backtest output/backtest_validation.json \
        --database postgresql://scp:password@localhost:5432/scp

    # Compare using pre-collected microservices trades
    poetry run python scripts/compare_results.py \
        --backtest output/backtest_validation.json \
        --microservices output/microservices_trades.json

    # Save detailed report
    poetry run python scripts/compare_results.py \
        --backtest output/backtest_validation.json \
        --database postgresql://scp:password@localhost:5432/scp \
        --output output/comparison_report.json
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from backtester.results_io import load_results
from backtester.trade import Trade
from common.logger import get_logger, setup_logging
from common.config import load_config

logger = get_logger(__name__)


@dataclass
class TradeMatch:
    """Represents a matched trade pair."""
    
    backtest_trade: dict
    microservice_trade: dict
    match_quality: str  # "exact", "close", "loose"
    differences: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComparisonReport:
    """Results of backtester vs microservices comparison."""
    
    # Trade counts
    backtest_count: int = 0
    microservices_count: int = 0
    
    # Matching results
    matches: list[TradeMatch] = field(default_factory=list)
    mismatches: list[tuple[dict, dict]] = field(default_factory=list)
    missing_in_microservices: list[dict] = field(default_factory=list)
    extra_in_microservices: list[dict] = field(default_factory=list)
    
    # Summary statistics
    match_rate: float = 0.0
    exact_matches: int = 0
    close_matches: int = 0
    loose_matches: int = 0
    
    def add_match(self, bt_trade: dict, ms_trade: dict, quality: str, differences: dict) -> None:
        """Add a matched trade pair."""
        match = TradeMatch(
            backtest_trade=bt_trade,
            microservice_trade=ms_trade,
            match_quality=quality,
            differences=differences,
        )
        self.matches.append(match)
        
        if quality == "exact":
            self.exact_matches += 1
        elif quality == "close":
            self.close_matches += 1
        elif quality == "loose":
            self.loose_matches += 1
    
    def add_mismatch(self, bt_trade: dict, ms_trade: dict) -> None:
        """Add a mismatched trade pair."""
        self.mismatches.append((bt_trade, ms_trade))
    
    def add_missing_in_microservices(self, bt_trade: dict) -> None:
        """Add a trade that exists in backtester but not in microservices."""
        self.missing_in_microservices.append(bt_trade)
    
    def add_extra_in_microservices(self, ms_trade: dict) -> None:
        """Add a trade that exists in microservices but not in backtester."""
        self.extra_in_microservices.append(ms_trade)
    
    def calculate_statistics(self) -> None:
        """Calculate summary statistics."""
        total_matched = len(self.matches)
        total_possible = max(self.backtest_count, self.microservices_count)
        
        if total_possible > 0:
            self.match_rate = (total_matched / total_possible) * 100
        else:
            self.match_rate = 0.0
    
    def print_summary(self) -> None:
        """Print summary to console."""
        logger.info("=" * 80)
        logger.info("Comparison Summary")
        logger.info("=" * 80)
        logger.info(f"Backtester trades: {self.backtest_count}")
        logger.info(f"Microservices trades: {self.microservices_count}")
        logger.info("")
        logger.info(f"Matches: {len(self.matches)} ({self.match_rate:.1f}%)")
        logger.info(f"  - Exact matches: {self.exact_matches}")
        logger.info(f"  - Close matches: {self.close_matches}")
        logger.info(f"  - Loose matches: {self.loose_matches}")
        logger.info(f"Mismatches: {len(self.mismatches)}")
        logger.info(f"Missing in microservices: {len(self.missing_in_microservices)}")
        logger.info(f"Extra in microservices: {len(self.extra_in_microservices)}")
        logger.info("=" * 80)
    
    def to_dict(self) -> dict:
        """Convert report to dictionary for JSON serialization."""
        return {
            "summary": {
                "backtest_count": self.backtest_count,
                "microservices_count": self.microservices_count,
                "match_rate": self.match_rate,
                "exact_matches": self.exact_matches,
                "close_matches": self.close_matches,
                "loose_matches": self.loose_matches,
                "mismatches": len(self.mismatches),
                "missing_in_microservices": len(self.missing_in_microservices),
                "extra_in_microservices": len(self.extra_in_microservices),
            },
            "matches": [
                {
                    "backtest_trade_id": m.backtest_trade["trade_id"],
                    "microservice_trade_id": m.microservice_trade["trade_id"],
                    "match_quality": m.match_quality,
                    "differences": m.differences,
                }
                for m in self.matches
            ],
            "mismatches": [
                {
                    "backtest_trade": bt,
                    "microservice_trade": ms,
                }
                for bt, ms in self.mismatches
            ],
            "missing_in_microservices": self.missing_in_microservices,
            "extra_in_microservices": self.extra_in_microservices,
        }


def parse_timestamp(ts: str | datetime | None) -> datetime | None:
    """Parse timestamp from various formats."""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts)


def trades_match_relaxed(
    bt_trade: dict,
    ms_trade: dict,
    timestamp_tolerance: timedelta = timedelta(minutes=1),
    price_tolerance: float = 0.5,
    sl_tp_tolerance: float = 1.0,
) -> tuple[bool, str, dict]:
    """Check if two trades match using relaxed criteria.
    
    Args:
        bt_trade: Backtester trade dictionary
        ms_trade: Microservices trade dictionary
        timestamp_tolerance: Maximum time difference for timestamp matching
        price_tolerance: Maximum price difference for entry price (in points)
        sl_tp_tolerance: Maximum price difference for SL/TP (in points)
        
    Returns:
        Tuple of (matches, quality, differences)
        - matches: True if trades match
        - quality: "exact", "close", or "loose"
        - differences: Dictionary of detected differences
    """
    differences = {}
    
    # Parse timestamps
    bt_entry_ts = parse_timestamp(bt_trade.get("entry_timestamp"))
    ms_entry_ts = parse_timestamp(ms_trade.get("entry_timestamp"))
    
    # Check timestamp proximity
    if bt_entry_ts is None or ms_entry_ts is None:
        differences["timestamp"] = "Missing timestamp"
        return False, "none", differences
    
    time_diff = abs((bt_entry_ts - ms_entry_ts).total_seconds())
    if time_diff > timestamp_tolerance.total_seconds():
        differences["timestamp"] = f"Time difference: {time_diff:.1f}s"
        return False, "none", differences
    
    # Check direction (must match exactly)
    bt_direction = bt_trade.get("direction")
    ms_direction = ms_trade.get("direction")
    
    if bt_direction != ms_direction:
        differences["direction"] = f"{bt_direction} vs {ms_direction}"
        return False, "none", differences
    
    # Check setup type (must match exactly)
    bt_setup = bt_trade.get("setup_type")
    ms_setup = ms_trade.get("setup_type")
    
    if bt_setup != ms_setup:
        differences["setup_type"] = f"{bt_setup} vs {ms_setup}"
        return False, "none", differences
    
    # Check entry price (relaxed tolerance)
    bt_entry = bt_trade.get("entry_price")
    ms_entry = ms_trade.get("entry_price")
    
    if bt_entry is None or ms_entry is None:
        differences["entry_price"] = "Missing entry price"
        return False, "none", differences
    
    entry_diff = abs(bt_entry - ms_entry)
    if entry_diff > price_tolerance:
        differences["entry_price"] = f"Difference: {entry_diff:.2f} points"
        return False, "none", differences
    
    # Track quality based on entry price match
    quality = "exact" if entry_diff < 0.01 else "close"
    
    # Check SL price (relaxed tolerance)
    bt_sl = bt_trade.get("stop_loss")
    ms_sl = ms_trade.get("stop_loss")
    
    if bt_sl is not None and ms_sl is not None:
        sl_diff = abs(bt_sl - ms_sl)
        if sl_diff > sl_tp_tolerance:
            differences["stop_loss"] = f"Difference: {sl_diff:.2f} points"
            quality = "loose"
        elif sl_diff > 0.1:
            quality = max(quality, "close")
    
    # Check TP price (relaxed tolerance)
    bt_tp = bt_trade.get("take_profit")
    ms_tp = ms_trade.get("take_profit")
    
    if bt_tp is not None and ms_tp is not None:
        tp_diff = abs(bt_tp - ms_tp)
        if tp_diff > sl_tp_tolerance:
            differences["take_profit"] = f"Difference: {tp_diff:.2f} points"
            quality = "loose"
        elif tp_diff > 0.1:
            quality = max(quality, "close")
    
    # Check exit reason (category match)
    bt_exit_reason = (bt_trade.get("exit_reason") or "").lower()
    ms_exit_reason = (ms_trade.get("exit_reason") or "").lower()
    
    if bt_exit_reason and ms_exit_reason:
        # Categorize exit reasons
        tp_reasons = ["tp", "take_profit"]
        sl_reasons = ["sl", "stop_loss"]
        invalidation_reasons = ["invalidation", "vwap_invalidation", "htf_invalidation", "dxy_flip"]
        
        bt_is_tp = any(r in bt_exit_reason for r in tp_reasons)
        ms_is_tp = any(r in ms_exit_reason for r in tp_reasons)
        
        bt_is_sl = any(r in bt_exit_reason for r in sl_reasons)
        ms_is_sl = any(r in ms_exit_reason for r in sl_reasons)
        
        bt_is_invalid = any(r in bt_exit_reason for r in invalidation_reasons)
        ms_is_invalid = any(r in ms_exit_reason for r in invalidation_reasons)
        
        # Exit reasons should be in the same category
        if not ((bt_is_tp and ms_is_tp) or (bt_is_sl and ms_is_sl) or (bt_is_invalid and ms_is_invalid)):
            differences["exit_reason"] = f"{bt_exit_reason} vs {ms_exit_reason}"
            quality = "loose"
    
    return True, quality, differences


def compare_backtest_vs_microservices(
    backtest_trades: list[dict],
    microservice_trades: list[dict],
) -> ComparisonReport:
    """Compare backtester trades against microservices trades.
    
    Args:
        backtest_trades: List of backtester trade dictionaries
        microservice_trades: List of microservices trade dictionaries
        
    Returns:
        ComparisonReport with detailed analysis
    """
    logger.info("=" * 80)
    logger.info("Comparing Trades")
    logger.info("=" * 80)
    logger.info(f"Backtester trades: {len(backtest_trades)}")
    logger.info(f"Microservices trades: {len(microservice_trades)}")
    
    report = ComparisonReport(
        backtest_count=len(backtest_trades),
        microservices_count=len(microservice_trades),
    )
    
    # Build index of microservices trades by timestamp (for faster lookup)
    ms_by_timestamp = {}
    for ms_trade in microservice_trades:
        ts = parse_timestamp(ms_trade.get("entry_timestamp"))
        if ts:
            # Use 1-minute buckets for matching
            bucket = ts.replace(second=0, microsecond=0)
            if bucket not in ms_by_timestamp:
                ms_by_timestamp[bucket] = []
            ms_by_timestamp[bucket].append(ms_trade)
    
    matched_ms_ids = set()
    
    # Match backtester trades
    for bt_trade in backtest_trades:
        bt_ts = parse_timestamp(bt_trade.get("entry_timestamp"))
        if not bt_ts:
            report.add_missing_in_microservices(bt_trade)
            continue
        
        # Look in current bucket and adjacent buckets (±1 minute)
        bucket = bt_ts.replace(second=0, microsecond=0)
        candidates = []
        
        for offset in [-1, 0, 1]:
            search_bucket = bucket + timedelta(minutes=offset)
            candidates.extend(ms_by_timestamp.get(search_bucket, []))
        
        # Find best match
        best_match = None
        best_quality = None
        best_differences = None
        
        for ms_trade in candidates:
            # Skip already matched trades
            if ms_trade.get("trade_id") in matched_ms_ids:
                continue
            
            matches, quality, differences = trades_match_relaxed(bt_trade, ms_trade)
            
            if matches:
                # Prefer higher quality matches
                quality_order = {"exact": 3, "close": 2, "loose": 1}
                if best_match is None or quality_order.get(quality, 0) > quality_order.get(best_quality, 0):
                    best_match = ms_trade
                    best_quality = quality
                    best_differences = differences
        
        if best_match:
            report.add_match(bt_trade, best_match, best_quality, best_differences)
            matched_ms_ids.add(best_match.get("trade_id"))
        else:
            report.add_missing_in_microservices(bt_trade)
    
    # Find extra trades in microservices
    for ms_trade in microservice_trades:
        if ms_trade.get("trade_id") not in matched_ms_ids:
            report.add_extra_in_microservices(ms_trade)
    
    report.calculate_statistics()
    
    return report


async def load_microservice_trades_from_db(database_url: str, start: datetime | None, end: datetime | None) -> list[dict]:
    """Load microservices trades from database."""
    from scripts.collect_microservice_trades import collect_trades
    
    logger.info("Loading microservices trades from database...")
    trades = await collect_trades(database_url, start, end)
    logger.info(f"Loaded {len(trades)} trades from database")
    
    return trades


def load_microservice_trades_from_json(filepath: Path) -> list[dict]:
    """Load microservices trades from JSON file."""
    logger.info(f"Loading microservices trades from {filepath}...")
    
    with open(filepath) as f:
        data = json.load(f)
    
    trades = data.get("trades", [])
    logger.info(f"Loaded {len(trades)} trades from JSON")
    
    return trades


def save_report(report: ComparisonReport, output_file: Path) -> None:
    """Save comparison report to JSON file."""
    logger.info(f"\nSaving report to {output_file}...")
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    output_data = {
        "generated_at": datetime.now().isoformat(),
        "report": report.to_dict(),
    }
    
    with open(output_file, "w") as f:
        json.dump(output_data, f, indent=2)
    
    logger.info(f"Report saved to {output_file}")


def build_arg_parser() -> argparse.ArgumentParser:
    """Build command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Compare backtester results with microservices results"
    )
    
    # Backtester results (required)
    parser.add_argument(
        "--backtest",
        type=Path,
        required=True,
        help="Backtester results JSON file",
    )
    
    # Microservices source (one of these required)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--database",
        type=str,
        help="PostgreSQL database URL to query trades",
    )
    group.add_argument(
        "--microservices",
        type=Path,
        help="Microservices trades JSON file",
    )
    
    # Date range filters (for database query)
    parser.add_argument(
        "--start",
        type=lambda s: datetime.fromisoformat(s),
        help="Start datetime filter for database query (ISO-8601)",
    )
    parser.add_argument(
        "--end",
        type=lambda s: datetime.fromisoformat(s),
        help="End datetime filter for database query (ISO-8601)",
    )
    
    # Output
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for detailed report (JSON)",
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
    
    # Validate inputs
    if not args.backtest.exists():
        logger.error(f"Backtest results file not found: {args.backtest}")
        sys.exit(1)
    
    if args.microservices and not args.microservices.exists():
        logger.error(f"Microservices results file not found: {args.microservices}")
        sys.exit(1)
    
    try:
        # Load backtester results
        logger.info(f"Loading backtester results from {args.backtest}...")
        backtest_results = load_results(args.backtest)
        
        # Convert Trade objects to dictionaries
        from backtester.trade import to_dict
        backtest_trades = [to_dict(trade) for trade in backtest_results.trades]
        logger.info(f"Loaded {len(backtest_trades)} backtester trades")
        
        # Load microservices trades
        if args.database:
            microservice_trades = await load_microservice_trades_from_db(
                args.database,
                args.start,
                args.end,
            )
        else:
            microservice_trades = load_microservice_trades_from_json(args.microservices)
        
        # Compare trades
        report = compare_backtest_vs_microservices(backtest_trades, microservice_trades)
        
        # Print summary
        report.print_summary()
        
        # Save detailed report if requested
        if args.output:
            save_report(report, args.output)
        
        # Determine exit code based on results
        if report.match_rate >= 90.0:
            logger.info("\n✓ Validation PASSED (match rate >= 90%)")
            sys.exit(0)
        else:
            logger.warning(f"\n✗ Validation FAILED (match rate {report.match_rate:.1f}% < 90%)")
            sys.exit(1)
    
    except Exception as e:
        logger.error(f"\nComparison failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())




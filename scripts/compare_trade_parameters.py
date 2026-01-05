#!/usr/bin/env python3
"""Compare backtester trades with microservices data.

This script takes every trade from the backtester results and pulls the relevant
data from the database to create a detailed comparison report showing differences
between the two implementations.

Usage:
    poetry run python scripts/compare_trade_parameters.py [OPTIONS]

Options:
    --backtest-file FILE    Path to backtest results JSON (default: auto-detect latest)
    --output FILE           Output comparison report path
    --db-url URL            Database connection URL

Example:
    poetry run python scripts/compare_trade_parameters.py \
        --backtest-file output/backtest_results_20251101_20251130.json \
        --output output/parameter_comparison.json
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import asyncpg

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
# Add shared library to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "shared" / "src"))

from common.logger import get_logger

# Import session validator
try:
    from scp_shared.validation.session_validator import SessionValidator
    SESSION_VALIDATOR_AVAILABLE = True
except ImportError:
    SESSION_VALIDATOR_AVAILABLE = False

logger = get_logger(__name__)


@dataclass
class FeatureComparison:
    """Comparison of a single feature between backtester and microservices."""
    
    feature_name: str
    backtester_value: Any
    microservices_value: Any
    match: bool
    difference: float | None = None  # For numeric values
    
    def to_dict(self) -> dict:
        return {
            "feature": self.feature_name,
            "backtester": self.backtester_value,
            "microservices": self.microservices_value,
            "match": self.match,
            "difference": self.difference,
        }


@dataclass
class TradeComparison:
    """Detailed comparison for a single trade."""
    
    trade_id: str
    signal_timestamp: str
    entry_timestamp: str
    direction: str
    setup_type: str
    
    # Backtester data
    backtester_score: float
    backtester_confidence: str
    backtester_htf_bias: str
    backtester_factors: dict
    backtester_features: dict
    backtester_validation_flags: dict
    
    # Microservices data (from DB)
    microservices_features: dict | None = None
    microservices_htf_bias: dict | None = None
    microservices_available: bool = False
    
    # Session validation
    session_validation: dict = field(default_factory=dict)
    
    # Blocking factors (why microservices wouldn't take this trade)
    blocking_factors: list[str] = field(default_factory=list)
    would_microservices_trade: bool = True
    
    # Comparison results
    feature_comparisons: list[FeatureComparison] = field(default_factory=list)
    htf_bias_comparisons: list[FeatureComparison] = field(default_factory=list)
    
    # Summary
    features_matching: int = 0
    features_mismatched: int = 0
    htf_matching: int = 0
    htf_mismatched: int = 0
    
    def to_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "signal_timestamp": self.signal_timestamp,
            "entry_timestamp": self.entry_timestamp,
            "direction": self.direction,
            "setup_type": self.setup_type,
            "backtester": {
                "score": self.backtester_score,
                "confidence": self.backtester_confidence,
                "htf_bias": self.backtester_htf_bias,
                "factors": self.backtester_factors,
                "features": self.backtester_features,
                "validation_flags": self.backtester_validation_flags,
            },
            "microservices": {
                "available": self.microservices_available,
                "features": self.microservices_features,
                "htf_bias": self.microservices_htf_bias,
            },
            "session_validation": self.session_validation,
            "would_microservices_trade": self.would_microservices_trade,
            "blocking_factors": self.blocking_factors,
            "comparison": {
                "features": [c.to_dict() for c in self.feature_comparisons],
                "htf_bias": [c.to_dict() for c in self.htf_bias_comparisons],
                "summary": {
                    "features_matching": self.features_matching,
                    "features_mismatched": self.features_mismatched,
                    "htf_matching": self.htf_matching,
                    "htf_mismatched": self.htf_mismatched,
                },
            },
        }


def load_backtest_results(file_path: Path) -> dict:
    """Load backtest results from JSON file."""
    logger.info(f"Loading backtest results from {file_path}")
    
    with open(file_path) as f:
        data = json.load(f)
    
    trades = data.get("trades", [])
    logger.info(f"Loaded {len(trades)} trades from backtest results")
    
    return data


async def query_features_at_timestamp(
    conn: asyncpg.Connection,
    timestamp: datetime,
    symbol: str = "GC",
    timeframe: str = "1m",
) -> dict | None:
    """Query features from database at specific timestamp."""
    
    # Look for exact match or closest before
    query = """
        SELECT 
            timestamp,
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
        "close": float(row["close"]) if row["close"] else None,
        "vwap": float(row["vwap"]) if row["vwap"] else None,
        "rsi": float(row["rsi"]) if row["rsi"] else None,
        "ema_9": float(row["ema_9"]) if row["ema_9"] else None,
        "ema_20": float(row["ema_20"]) if row["ema_20"] else None,
        "ema_50": float(row["ema_50"]) if row["ema_50"] else None,
        "dxy_correlation": float(row["dxy_correlation"]) if row["dxy_correlation"] else None,
        "structure_label": row["structure_label"],
        "vwap_deviation": float(row["vwap_deviation"]) if row["vwap_deviation"] else None,
    }


async def query_htf_bias_at_timestamp(
    conn: asyncpg.Connection,
    timestamp: datetime,
) -> dict | None:
    """Query HTF bias from database at specific timestamp."""
    
    # Look for the most recent HTF bias before the signal timestamp
    query = """
        SELECT 
            timestamp,
            bias,
            score,
            confidence,
            structure_15m,
            structure_1h,
            dxy_aligned,
            chop_detected
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
    }


def compare_values(
    name: str,
    backtester_val: Any,
    microservices_val: Any,
    tolerance: float = 0.01,
) -> FeatureComparison:
    """Compare two values and return comparison result."""
    
    # Handle None/missing values
    if backtester_val is None and microservices_val is None:
        return FeatureComparison(name, backtester_val, microservices_val, True)
    
    if backtester_val is None or microservices_val is None:
        return FeatureComparison(name, backtester_val, microservices_val, False)
    
    # Handle NaN
    import math
    if isinstance(backtester_val, float) and math.isnan(backtester_val):
        backtester_val = None
    if isinstance(microservices_val, float) and math.isnan(microservices_val):
        microservices_val = None
    
    if backtester_val is None and microservices_val is None:
        return FeatureComparison(name, backtester_val, microservices_val, True)
    if backtester_val is None or microservices_val is None:
        return FeatureComparison(name, backtester_val, microservices_val, False)
    
    # Numeric comparison with tolerance
    if isinstance(backtester_val, (int, float)) and isinstance(microservices_val, (int, float)):
        diff = abs(backtester_val - microservices_val)
        match = diff < tolerance
        return FeatureComparison(name, backtester_val, microservices_val, match, diff)
    
    # String/boolean comparison
    match = str(backtester_val).lower() == str(microservices_val).lower()
    return FeatureComparison(name, backtester_val, microservices_val, match)


def extract_backtester_features(trade: dict) -> dict:
    """Extract feature values from backtester trade data."""
    
    diagnostics = trade.get("diagnostics", {})
    entry_context = diagnostics.get("entry_context", {})
    
    return {
        "vwap": entry_context.get("vwap"),
        "vwap_deviation": entry_context.get("vwap_deviation"),
        "rsi": entry_context.get("rsi"),
        "structure_label": entry_context.get("structure_label"),
        "liquidity_sweep": entry_context.get("liquidity_sweep"),
        "vwap_slope": entry_context.get("vwap_slope"),
        "volume": entry_context.get("volume"),
        "volume_sma_20": entry_context.get("volume_sma_20"),
    }


def check_session_validation(signal_ts: datetime) -> dict:
    """Check if session validation would allow this trade."""
    if not SESSION_VALIDATOR_AVAILABLE:
        return {"available": False, "reason": "SessionValidator not available"}
    
    try:
        from scp_shared.validation.config_loader import load_session_config
        
        config = load_session_config()
        validator = SessionValidator(config)
        result = validator.evaluate(signal_ts)
        return {
            "available": True,
            "session_ok": result.session_ok,
            "season": result.constraints.name if result.constraints else None,
            "rejection_reason": result.reason,
            "window": f"{result.constraints.window_start.strftime('%H:%M')}-{result.constraints.window_end.strftime('%H:%M')}" if result.constraints else None,
            "timestamp_utc": signal_ts.isoformat(),
        }
    except Exception as e:
        return {"available": False, "reason": str(e)}


async def compare_single_trade(
    trade: dict,
    conn: asyncpg.Connection,
) -> TradeComparison:
    """Compare a single trade with microservices data."""
    
    # Extract trade info
    entry_execution = trade.get("entry_execution", {})
    signal = entry_execution.get("signal", {})
    signal_ts_str = signal.get("timestamp") or entry_execution.get("signal_timestamp")
    
    # Parse timestamp
    signal_ts = datetime.fromisoformat(signal_ts_str.replace("Z", "+00:00"))
    
    # Extract backtester data
    backtester_features = extract_backtester_features(trade)
    
    comparison = TradeComparison(
        trade_id=trade.get("trade_id", "unknown"),
        signal_timestamp=signal_ts_str,
        entry_timestamp=trade.get("entry_timestamp", ""),
        direction=trade.get("direction", ""),
        setup_type=trade.get("setup_type", ""),
        backtester_score=signal.get("score", 0),
        backtester_confidence=signal.get("confidence", ""),
        backtester_htf_bias=signal.get("htf_bias", ""),
        backtester_factors=signal.get("factors", {}),
        backtester_features=backtester_features,
        backtester_validation_flags=signal.get("validation_flags", {}),
    )
    
    # Check session validation
    comparison.session_validation = check_session_validation(signal_ts)
    
    # Query microservices data
    ms_features = await query_features_at_timestamp(conn, signal_ts)
    ms_htf_bias = await query_htf_bias_at_timestamp(conn, signal_ts)
    
    comparison.microservices_features = ms_features
    comparison.microservices_htf_bias = ms_htf_bias
    comparison.microservices_available = ms_features is not None or ms_htf_bias is not None
    
    # Determine blocking factors
    blocking_factors = []
    
    # Check session
    if comparison.session_validation.get("available"):
        if not comparison.session_validation.get("session_ok"):
            reason = comparison.session_validation.get("rejection_reason", "unknown")
            blocking_factors.append(f"SESSION_BLOCKED: {reason}")
    
    # Check HTF bias
    if ms_htf_bias:
        ms_bias = ms_htf_bias.get("bias")
        ms_confidence = ms_htf_bias.get("confidence")
        ms_chop = ms_htf_bias.get("chop_detected")
        ms_structure_1h = ms_htf_bias.get("structure_1h")
        ms_structure_15m = ms_htf_bias.get("structure_15m")
        
        # Check if bias is neutral
        if ms_bias == "neutral":
            blocking_factors.append(f"HTF_BIAS_NEUTRAL: score={ms_htf_bias.get('score')}")
        
        # Check if bias conflicts with direction
        expected_bias = "bullish" if comparison.direction == "long" else "bearish"
        if ms_bias and ms_bias != expected_bias and ms_bias != "neutral":
            blocking_factors.append(f"HTF_BIAS_CONFLICT: expected={expected_bias}, got={ms_bias}")
        
        # Check confidence
        if ms_confidence and ms_confidence not in ("A+", "A"):
            blocking_factors.append(f"HTF_CONFIDENCE_LOW: {ms_confidence}")
        
        # Check chop - NOTE: chop is NOT a blocking factor for VWAP_RECLAIM
        # Only flag it for informational purposes, not as a blocker
        # if ms_chop and comparison.setup_type != "VWAP_RECLAIM":
        #     blocking_factors.append("CHOP_DETECTED")
        pass  # Chop penalty disabled for parity testing
        
        # Check structure labels
        if ms_structure_1h is None:
            blocking_factors.append("HTF_STRUCTURE_1H_NULL")
        if ms_structure_15m is None:
            blocking_factors.append("HTF_STRUCTURE_15M_NULL")
    else:
        blocking_factors.append("NO_HTF_BIAS_DATA")
    
    comparison.blocking_factors = blocking_factors
    comparison.would_microservices_trade = len(blocking_factors) == 0
    
    # Compare features
    if ms_features:
        feature_mappings = [
            ("vwap", "vwap"),
            ("vwap_deviation", "vwap_deviation"),
            ("rsi", "rsi"),
            ("structure_label", "structure_label"),
        ]
        
        for bt_key, ms_key in feature_mappings:
            bt_val = backtester_features.get(bt_key)
            ms_val = ms_features.get(ms_key)
            cmp = compare_values(bt_key, bt_val, ms_val)
            comparison.feature_comparisons.append(cmp)
            if cmp.match:
                comparison.features_matching += 1
            else:
                comparison.features_mismatched += 1
    
    # Compare HTF bias
    if ms_htf_bias:
        htf_mappings = [
            ("htf_bias", "bias", comparison.backtester_htf_bias),
            ("structure_1h", "structure_1h", None),  # Need to get from backtester if available
            ("structure_15m", "structure_15m", None),
            ("chop_detected", "chop_detected", None),
            ("dxy_aligned", "dxy_aligned", None),
        ]
        
        for name, ms_key, bt_val in htf_mappings:
            if bt_val is None:
                # Try to get from signal rationale or factors
                continue
            ms_val = ms_htf_bias.get(ms_key)
            cmp = compare_values(name, bt_val, ms_val)
            comparison.htf_bias_comparisons.append(cmp)
            if cmp.match:
                comparison.htf_matching += 1
            else:
                comparison.htf_mismatched += 1
    
    return comparison


async def run_comparison(
    backtest_file: Path,
    db_url: str,
    output_file: Path,
) -> dict:
    """Run the full comparison and generate report."""
    
    # Load backtest results
    backtest_data = load_backtest_results(backtest_file)
    trades = backtest_data.get("trades", [])
    
    if not trades:
        logger.warning("No trades found in backtest results")
        return {"error": "No trades found"}
    
    # Connect to database
    logger.info(f"Connecting to database...")
    
    try:
        conn = await asyncpg.connect(db_url)
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        return {"error": f"Database connection failed: {e}"}
    
    try:
        # Check what data is available
        feature_count = await conn.fetchval("SELECT COUNT(*) FROM features")
        htf_count = await conn.fetchval("SELECT COUNT(*) FROM htf_bias_history")
        
        logger.info(f"Database has {feature_count} feature rows, {htf_count} HTF bias rows")
        
        # Compare each trade
        comparisons = []
        for i, trade in enumerate(trades, 1):
            logger.info(f"Comparing trade {i}/{len(trades)}: {trade.get('trade_id', 'unknown')}")
            comparison = await compare_single_trade(trade, conn)
            comparisons.append(comparison)
        
        # Build report
        report = {
            "generated_at": datetime.now().isoformat(),
            "backtest_file": str(backtest_file),
            "database_stats": {
                "feature_rows": feature_count,
                "htf_bias_rows": htf_count,
            },
            "summary": {
                "total_trades": len(trades),
                "trades_with_microservices_data": sum(
                    1 for c in comparisons if c.microservices_available
                ),
                "trades_missing_microservices_data": sum(
                    1 for c in comparisons if not c.microservices_available
                ),
                "total_feature_comparisons": sum(
                    len(c.feature_comparisons) for c in comparisons
                ),
                "total_feature_matches": sum(c.features_matching for c in comparisons),
                "total_feature_mismatches": sum(c.features_mismatched for c in comparisons),
            },
            "trade_comparisons": [c.to_dict() for c in comparisons],
        }
        
        # Calculate per-feature mismatch breakdown
        feature_mismatch_counts: dict[str, int] = {}
        for c in comparisons:
            for fc in c.feature_comparisons:
                if not fc.match:
                    feature_mismatch_counts[fc.feature_name] = (
                        feature_mismatch_counts.get(fc.feature_name, 0) + 1
                    )
        
        report["feature_mismatch_breakdown"] = feature_mismatch_counts
        
        # Calculate blocking factor breakdown
        blocking_factor_counts: dict[str, int] = {}
        for c in comparisons:
            for bf in c.blocking_factors:
                # Extract category (before colon)
                category = bf.split(":")[0]
                blocking_factor_counts[category] = blocking_factor_counts.get(category, 0) + 1
        
        report["blocking_factor_breakdown"] = blocking_factor_counts
        
        # Add trade-by-trade blocking summary
        trades_would_be_taken = sum(1 for c in comparisons if c.would_microservices_trade)
        trades_would_be_blocked = sum(1 for c in comparisons if not c.would_microservices_trade)
        
        report["summary"]["trades_would_pass_microservices"] = trades_would_be_taken
        report["summary"]["trades_would_be_blocked"] = trades_would_be_blocked
        
        # Save report
        logger.info(f"Saving comparison report to {output_file}")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2, default=str)
        
        # Print summary
        print("\n" + "=" * 70)
        print("COMPARISON SUMMARY")
        print("=" * 70)
        print(f"Total trades analyzed: {len(trades)}")
        print(f"Trades with microservices data: {report['summary']['trades_with_microservices_data']}")
        print(f"Trades missing data: {report['summary']['trades_missing_microservices_data']}")
        print(f"\nFeature comparisons:")
        print(f"  Matches: {report['summary']['total_feature_matches']}")
        print(f"  Mismatches: {report['summary']['total_feature_mismatches']}")
        
        if feature_mismatch_counts:
            print(f"\nMismatch breakdown by feature:")
            for feature, count in sorted(feature_mismatch_counts.items(), key=lambda x: -x[1]):
                print(f"  {feature}: {count} mismatches")
        
        print(f"\n" + "-" * 70)
        print("BLOCKING FACTOR ANALYSIS")
        print("-" * 70)
        print(f"Trades that would PASS microservices: {trades_would_be_taken}")
        print(f"Trades that would be BLOCKED: {trades_would_be_blocked}")
        
        if blocking_factor_counts:
            print(f"\nBlocking factors (why trades wouldn't execute in microservices):")
            for factor, count in sorted(blocking_factor_counts.items(), key=lambda x: -x[1]):
                print(f"  {factor}: {count} trades blocked")
        
        print(f"\n" + "-" * 70)
        print("TRADE-BY-TRADE BLOCKING FACTORS")
        print("-" * 70)
        for c in comparisons:
            status = "✓ PASS" if c.would_microservices_trade else "✗ BLOCKED"
            print(f"\n{c.trade_id[:8]}... ({c.signal_timestamp}) - {status}")
            if c.blocking_factors:
                for bf in c.blocking_factors:
                    print(f"    → {bf}")
            else:
                print(f"    → No blocking factors")
        
        print(f"\n" + "=" * 70)
        print(f"Full report saved to: {output_file}")
        print("=" * 70)
        
        return report
        
    finally:
        await conn.close()


def find_latest_backtest_file() -> Path:
    """Find the most recent backtest results file."""
    output_dir = Path(__file__).parent.parent / "output"
    
    pattern = "backtest_results_*.json"
    files = list(output_dir.glob(pattern))
    
    if not files:
        raise FileNotFoundError(f"No backtest results found in {output_dir}")
    
    # Sort by modification time, get latest
    latest = max(files, key=lambda p: p.stat().st_mtime)
    return latest


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Compare backtester trades with microservices database"
    )
    parser.add_argument(
        "--backtest-file",
        type=Path,
        default=None,
        help="Path to backtest results JSON (default: auto-detect latest)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output comparison report path (default: output/parameter_comparison_<timestamp>.json)",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default="postgresql://scp:scp_dev_password@localhost:5432/scp",
        help="Database connection URL",
    )
    
    args = parser.parse_args()
    
    # Find backtest file
    if args.backtest_file:
        backtest_file = args.backtest_file
    else:
        try:
            backtest_file = find_latest_backtest_file()
            logger.info(f"Auto-detected backtest file: {backtest_file}")
        except FileNotFoundError as e:
            logger.error(str(e))
            sys.exit(1)
    
    if not backtest_file.exists():
        logger.error(f"Backtest file not found: {backtest_file}")
        sys.exit(1)
    
    # Set output file
    if args.output:
        output_file = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path(__file__).parent.parent / "output" / f"parameter_comparison_{timestamp}.json"
    
    # Run comparison
    asyncio.run(run_comparison(backtest_file, args.db_url, output_file))


if __name__ == "__main__":
    main()


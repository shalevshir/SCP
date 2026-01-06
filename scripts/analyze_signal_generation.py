#!/usr/bin/env python3
"""Analyze signal generation differences between backtester and microservices.

This script investigates why the same features produce different signals/trades.
Focuses on the scoring, validation, and guardrails layers.

Usage:
    poetry run python scripts/analyze_signal_generation.py \
        --backtest output/backtest_validation.json \
        --start 2025-11-05 --end 2025-11-11
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from backtester.results_io import load_results
from common.config import load_config
from common.logger import get_logger, setup_logging
from common.types import Candle as BacktesterCandle
from data_layer.multi_timeframe_helpers import extract_execution_dataframes
from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer
from scp_shared.common.types import Candle as MicroservicesCandle
from scp_shared.database import DatabasePool

logger = get_logger(__name__)


class SignalGenerationAnalyzer:
    """Analyzes signal generation differences between implementations."""

    def __init__(
        self,
        backtest_file: Path,
        data_path: str,
        database_url: str,
        start: datetime,
        end: datetime,
    ):
        """Initialize analyzer.

        Args:
            backtest_file: Path to backtester results JSON
            data_path: Path to historical data
            database_url: PostgreSQL connection string
            start: Start datetime
            end: End datetime
        """
        self.backtest_file = backtest_file
        self.data_path = data_path
        self.start = start
        self.end = end

        # Load backtester results
        logger.info(f"Loading backtester results from {backtest_file}")
        self.backtest_results = load_results(backtest_file)

        # Load historical data
        logger.info(f"Loading historical data from {data_path}")
        sync_layer = MultiTimeframeSyncLayer(data_path)
        multi_tf_data = sync_layer.load(start, end)
        self.gc_df, self.dxy_df = extract_execution_dataframes(multi_tf_data)

        # Database connection (will be connected in analyze())
        self.database_url = database_url
        self.db_pool = None

        # Initialize processors
        from feature_engine.streaming import (
            StreamingFeatureProcessor as BacktesterProcessor,
        )
        from rule_engine.htf.types import HTFBias as BTHTFBias
        from rule_engine.scoring import score_signal as bt_score_signal
        from scp_shared.indicators.streaming import (
            StreamingFeatureProcessor as MicroProcessor,
        )
        from scp_shared.rule_engine import score_signal as ms_score_signal
        from scp_shared.rule_engine.htf.types import HTFBias as MSHTFBias

        self.bt_processor = BacktesterProcessor(timeframe="1m")
        self.ms_processor = MicroProcessor(timeframe="1m")
        self.bt_score_signal = bt_score_signal
        self.ms_score_signal = ms_score_signal
        self.BTHTFBias = BTHTFBias
        self.MSHTFBias = MSHTFBias

    async def analyze(self) -> dict:
        """Run full signal generation analysis.

        Returns:
            Analysis report dict
        """
        # Connect to database
        self.db_pool = DatabasePool(self.database_url)
        await self.db_pool.connect()

        try:
            return await self._analyze_impl()
        finally:
            await self.db_pool.close()

    async def _analyze_impl(self) -> dict:
        """Internal analysis implementation.

        Returns:
            Analysis report dict
        """
        logger.info("=" * 80)
        logger.info("Signal Generation Analysis")
        logger.info("=" * 80)

        # Extract signal timestamps from backtester trades
        signal_timestamps = []
        for trade in self.backtest_results.trades:
            signal_ts = trade.entry_execution.signal_timestamp
            signal_timestamps.append(
                {
                    "timestamp": signal_ts,
                    "trade_id": trade.trade_id,
                    "direction": trade.direction,
                    "setup_type": trade.setup_type,
                    "score": trade.entry_execution.signal.score,
                    "confidence": trade.entry_execution.signal.confidence,
                }
            )

        logger.info(f"Analyzing {len(signal_timestamps)} backtester signals")

        # Query microservices data for those timestamps
        signal_comparisons = []

        for sig_info in signal_timestamps:
            ts = sig_info["timestamp"]
            logger.info(f"\nAnalyzing signal at {ts}")

            # Get features from both implementations at this timestamp
            bt_features, ms_features = await self._get_features_at_timestamp(ts)

            # Get HTF bias from database
            htf_bias_bt, htf_bias_ms = await self._get_htf_bias_at_timestamp(ts)

            # Generate signals from both
            bt_signal = self._generate_backtester_signal(bt_features, htf_bias_bt)
            ms_signal = self._generate_microservices_signal(ms_features, htf_bias_ms)

            # Compare
            comparison = self._compare_signals(
                sig_info,
                bt_signal,
                ms_signal,
                bt_features,
                ms_features,
                htf_bias_bt,
                htf_bias_ms,
            )

            signal_comparisons.append(comparison)

        # Query for extra microservices trades (not in backtester)
        extra_trades = await self._find_extra_microservices_trades()

        # Build report
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "period": {
                "start": self.start.isoformat(),
                "end": self.end.isoformat(),
            },
            "summary": {
                "backtester_signals": len(signal_timestamps),
                "signal_comparisons": len(signal_comparisons),
                "extra_microservices_trades": len(extra_trades),
                "signals_matched": sum(
                    1 for c in signal_comparisons if c["signals_match"]
                ),
                "signals_mismatched": sum(
                    1 for c in signal_comparisons if not c["signals_match"]
                ),
            },
            "signal_comparisons": signal_comparisons,
            "extra_microservices_trades": extra_trades,
        }

        return report

    async def _get_features_at_timestamp(self, ts: datetime) -> tuple:
        """Get features from both implementations at timestamp."""
        # Find the bar index for this timestamp
        try:
            bar_idx = self.gc_df.index.get_loc(ts)
        except KeyError:
            logger.warning(f"Timestamp {ts} not found in dataframe")
            return None, None

        # Replay both processors up to this point
        bt_proc = type(self.bt_processor)(timeframe="1m")
        ms_proc = type(self.ms_processor)(timeframe="1m")

        for i in range(bar_idx + 1):
            gc_row = self.gc_df.iloc[i]
            dxy_row = self.dxy_df.iloc[i]

            bt_candle = BacktesterCandle(
                timestamp=gc_row.name,
                open=float(gc_row["open"]),
                high=float(gc_row["high"]),
                low=float(gc_row["low"]),
                close=float(gc_row["close"]),
                volume=float(gc_row["volume"]),
                symbol="GC",
                timeframe="1m",
                source="ANALYSIS",
            )

            ms_candle = MicroservicesCandle(
                timestamp=gc_row.name,
                open=float(gc_row["open"]),
                high=float(gc_row["high"]),
                low=float(gc_row["low"]),
                close=float(gc_row["close"]),
                volume=float(gc_row["volume"]),
                symbol="GC",
                timeframe="1m",
                source="ANALYSIS",
            )

            bt_dxy = BacktesterCandle(
                timestamp=dxy_row.name,
                open=float(dxy_row["open"]),
                high=float(dxy_row["high"]),
                low=float(dxy_row["low"]),
                close=float(dxy_row["close"]),
                volume=float(dxy_row["volume"]),
                symbol="DXY",
                timeframe="1m",
                source="ANALYSIS",
            )

            ms_dxy = MicroservicesCandle(
                timestamp=dxy_row.name,
                open=float(dxy_row["open"]),
                high=float(dxy_row["high"]),
                low=float(dxy_row["low"]),
                close=float(dxy_row["close"]),
                volume=float(dxy_row["volume"]),
                symbol="DXY",
                timeframe="1m",
                source="ANALYSIS",
            )

            bt_features = bt_proc.update(bt_candle, bt_dxy)
            ms_features = ms_proc.update(ms_candle, ms_dxy)

        # Add required metadata
        if "symbol" not in bt_features.index:
            bt_features["symbol"] = "GC"
        if "timeframe" not in bt_features.index:
            bt_features["timeframe"] = "1m"
        if "symbol" not in ms_features.index:
            ms_features["symbol"] = "GC"
        if "timeframe" not in ms_features.index:
            ms_features["timeframe"] = "1m"

        return bt_features, ms_features

    async def _get_htf_bias_at_timestamp(self, ts: datetime) -> tuple:
        """Get HTF bias for timestamp from database."""
        # Query closest HTF bias before this timestamp
        result = await self.db_pool.fetchrow(
            """
            SELECT bias, score, confidence, structure_15m, structure_1h,
                   dxy_aligned, chop_detected
            FROM htf_bias_history
            WHERE timestamp <= $1
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            ts,
        )

        if result is None:
            logger.warning(f"No HTF bias found for {ts}, using neutral")
            # Create neutral bias
            bt_bias = self.BTHTFBias(
                bias="neutral",
                direction="neutral",
                score=5.0,
                confidence="low",
                structure_15m=None,
                structure_1h=None,
                dxy_alignment=False,
                chop_detected=False,
            )
            ms_bias = self.MSHTFBias(
                bias="neutral",
                direction="neutral",
                score=5.0,
                confidence="low",
                structure_15m=None,
                structure_1h=None,
                dxy_alignment=False,
                chop_detected=False,
            )
            return bt_bias, ms_bias

        # Map confidence
        confidence_map = {"A+": "high", "A": "high", "B": "medium", "C": "low"}
        direction_map = {"bullish": "long", "bearish": "short", "neutral": "neutral"}

        bt_bias = self.BTHTFBias(
            bias=result["bias"],
            direction=direction_map.get(result["bias"], "neutral"),
            score=float(result["score"]),
            confidence=confidence_map.get(result["confidence"], "low"),
            structure_15m=result["structure_15m"],
            structure_1h=result["structure_1h"],
            dxy_alignment=result["dxy_aligned"],
            chop_detected=result["chop_detected"],
        )

        ms_bias = self.MSHTFBias(
            bias=result["bias"],
            direction=direction_map.get(result["bias"], "neutral"),
            score=float(result["score"]),
            confidence=confidence_map.get(result["confidence"], "low"),
            structure_15m=result["structure_15m"],
            structure_1h=result["structure_1h"],
            dxy_alignment=result["dxy_aligned"],
            chop_detected=result["chop_detected"],
        )

        return bt_bias, ms_bias

    def _generate_backtester_signal(self, features, htf_bias):
        """Generate signal using backtester logic."""
        if features is None or htf_bias is None:
            return None

        context = {"session_ok": True, "enforcer_tier": "EarlyMild"}

        try:
            return self.bt_score_signal(features, htf_bias, context)
        except Exception as e:
            logger.error(f"Error generating backtester signal: {e}", exc_info=True)
            return None

    def _generate_microservices_signal(self, features, htf_bias):
        """Generate signal using microservices logic."""
        if features is None or htf_bias is None:
            return None

        context = {"session_ok": True, "enforcer_tier": "EarlyMild"}

        try:
            return self.ms_score_signal(features, htf_bias, context)
        except Exception as e:
            logger.error(f"Error generating microservices signal: {e}", exc_info=True)
            return None

    def _compare_signals(
        self,
        sig_info: dict,
        bt_signal,
        ms_signal,
        bt_features,
        ms_features,
        htf_bias_bt,
        htf_bias_ms,
    ) -> dict:
        """Compare signals and identify differences."""
        comparison = {
            "timestamp": sig_info["timestamp"].isoformat(),
            "backtester_trade": sig_info,
            "signals_match": False,
            "differences": [],
        }

        # Extract signal properties
        if bt_signal:
            comparison["backtester_signal"] = {
                "setup_type": bt_signal.setup_type,
                "direction": bt_signal.direction,
                "score": bt_signal.score,
                "confidence": bt_signal.confidence,
                "factors": bt_signal.factors,
            }
        else:
            comparison["backtester_signal"] = None

        if ms_signal:
            comparison["microservices_signal"] = {
                "setup_type": ms_signal.setup_type,
                "direction": ms_signal.direction,
                "score": ms_signal.score,
                "confidence": ms_signal.confidence,
                "factors": ms_signal.factors,
            }
        else:
            comparison["microservices_signal"] = None

        # Compare
        if bt_signal and ms_signal:
            if (
                bt_signal.setup_type == ms_signal.setup_type
                and bt_signal.direction == ms_signal.direction
                and bt_signal.confidence == ms_signal.confidence
            ):
                comparison["signals_match"] = True
            else:
                if bt_signal.setup_type != ms_signal.setup_type:
                    comparison["differences"].append("setup_type")
                if bt_signal.direction != ms_signal.direction:
                    comparison["differences"].append("direction")
                if bt_signal.confidence != ms_signal.confidence:
                    comparison["differences"].append("confidence")
                if abs(bt_signal.score - ms_signal.score) > 0.1:
                    comparison["differences"].append(
                        f"score ({bt_signal.score} vs {ms_signal.score})"
                    )
        elif bt_signal and not ms_signal:
            comparison["differences"].append("microservices_did_not_generate_signal")
        elif ms_signal and not bt_signal:
            comparison["differences"].append("backtester_did_not_generate_signal")

        # Add feature comparison
        if bt_features is not None and ms_features is not None:
            feature_diffs = []
            for key in ["rsi", "vwap", "structure_label", "vwap_deviation"]:
                bt_val = bt_features.get(key)
                ms_val = ms_features.get(key)
                if bt_val != ms_val:
                    feature_diffs.append(
                        {
                            "feature": key,
                            "backtester": bt_val,
                            "microservices": ms_val,
                        }
                    )
            comparison["feature_differences"] = feature_diffs

        return comparison

    async def _find_extra_microservices_trades(self) -> list:
        """Find trades in microservices that don't exist in backtester."""
        # Get all microservices trades in date range
        results = await self.db_pool.fetch(
            """
            SELECT id, direction, setup_type, opened_at, entry_price,
                   closed_at, exit_reason, pnl_points, r_multiple
            FROM trades
            WHERE opened_at >= $1 AND opened_at < $2
            ORDER BY opened_at
            """,
            self.start,
            self.end,
        )

        logger.info(f"Found {len(results)} microservices trades in period")
        logger.info(f"Backtester had {len(self.backtest_results.trades)} trades")

        # Build set of backtester entry timestamps (within 1 minute tolerance)
        bt_entry_times = set()
        for trade in self.backtest_results.trades:
            bt_entry_times.add(trade.entry_timestamp)

        # Find extras
        extra_trades = []
        for row in results:
            entry_ts = row["opened_at"]

            # Check if this matches any backtester trade (within 1 min)
            matched = False
            for bt_ts in bt_entry_times:
                if abs((entry_ts - bt_ts).total_seconds()) < 60:
                    matched = True
                    break

            if not matched:
                extra_trades.append(
                    {
                        "id": str(row["id"]),
                        "direction": row["direction"],
                        "setup_type": row["setup_type"],
                        "entry_timestamp": row["opened_at"].isoformat(),
                        "entry_price": float(row["entry_price"]),
                        "exit_timestamp": (
                            row["closed_at"].isoformat() if row["closed_at"] else None
                        ),
                        "exit_reason": row["exit_reason"],
                        "pnl": float(row["pnl_points"]) if row["pnl_points"] else None,
                        "r_realized": (
                            float(row["r_multiple"]) if row["r_multiple"] else None
                        ),
                    }
                )

        logger.info(f"Found {len(extra_trades)} extra microservices trades")

        return extra_trades


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze signal generation differences"
    )

    parser.add_argument(
        "--backtest",
        type=Path,
        required=True,
        help="Backtester results JSON file",
    )

    parser.add_argument(
        "--start",
        type=str,
        required=True,
        help="Start date (YYYY-MM-DD)",
    )

    parser.add_argument(
        "--end",
        type=str,
        required=True,
        help="End date (YYYY-MM-DD)",
    )

    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/gc_dx_ohlcv",
        help="Historical data directory",
    )

    parser.add_argument(
        "--database",
        type=str,
        default="postgresql://scp:scp_dev_password@localhost:5432/scp",
        help="PostgreSQL connection string",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file path",
    )

    return parser.parse_args()


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Setup logging
    project_root = Path(__file__).parent.parent
    config = load_config(project_root / "config" / "core.yaml")
    setup_logging(config.system)

    # Parse dates
    start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
    end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = Path(f"output/signal_analysis_{args.start}_{args.end}.json")

    try:
        # Run analysis
        analyzer = SignalGenerationAnalyzer(
            backtest_file=args.backtest,
            data_path=args.data_dir,
            database_url=args.database,
            start=start,
            end=end,
        )

        report = await analyzer.analyze()

        # Save report (with datetime serialization)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Custom JSON encoder for datetime objects
        class DateTimeEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                return super().default(obj)

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, cls=DateTimeEncoder)

        logger.info(f"\nReport saved to {output_path}")

        # Print summary
        print("\n" + "=" * 80)
        print("SIGNAL GENERATION ANALYSIS SUMMARY")
        print("=" * 80)
        print(f"Backtester signals analyzed: {report['summary']['backtester_signals']}")
        print(f"Signals matched: {report['summary']['signals_matched']}")
        print(f"Signals mismatched: {report['summary']['signals_mismatched']}")
        extra_count = report["summary"]["extra_microservices_trades"]
        print(f"Extra microservices trades: {extra_count}")
        print("=" * 80)

        return 0

    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))

#!/usr/bin/env python3
"""Side-by-side replay: Compare backtester and microservices bar-by-bar.

This script runs both implementations in-process on identical input data,
comparing outputs at each stage (features, signals, decisions) to identify
the exact bar and component where divergences occur.

Usage:
    # Single day comparison
    poetry run python scripts/side_by_side_replay.py --date 2024-11-06
    
    # Date range with stop on first divergence
    poetry run python scripts/side_by_side_replay.py \
        --start 2024-11-01 --end 2024-11-30 \
        --stop-on-first
    
    # With custom output path
    poetry run python scripts/side_by_side_replay.py \
        --date 2024-11-06 \
        --output output/divergence_2024-11-06.json
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from common.config import load_config
from common.logger import get_logger, setup_logging
from common.types import Candle as BacktesterCandle
from data_layer.multi_timeframe_helpers import extract_execution_dataframes
from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer
from scp_shared.common.types import Candle as MicroservicesCandle
from scripts.parity.comparators import compare_features, compare_signals
from scripts.parity.report import DivergenceReport

logger = get_logger(__name__)


class SideBySideReplay:
    """Orchestrates side-by-side comparison of backtester and microservices.

    Runs both implementations in-process on identical data, comparing outputs
    at each processing stage to identify divergences.
    """

    def __init__(
        self,
        data_path: str,
        start: datetime,
        end: datetime,
        stop_on_first_divergence: bool = False,
    ):
        """Initialize side-by-side replay.

        Args:
            data_path: Path to historical data directory
            start: Start datetime for comparison
            end: End datetime for comparison
            stop_on_first_divergence: Whether to stop on first divergence
        """
        self.data_path = data_path
        self.start = start
        self.end = end
        self.stop_on_first = stop_on_first_divergence

        # Load data
        logger.info(f"Loading data from {data_path}...")
        sync_layer = MultiTimeframeSyncLayer(data_path)
        self.multi_tf_data = sync_layer.load(start, end)

        # Extract execution DataFrames
        self.gc_df, self.dxy_df = extract_execution_dataframes(self.multi_tf_data)

        logger.info(
            f"Loaded {len(self.gc_df)} GC candles, {len(self.dxy_df)} DXY candles"
        )

        # Initialize backtester components
        logger.info("Initializing backtester components...")
        from feature_engine.streaming import (
            StreamingFeatureProcessor as BacktesterProcessor,
        )
        from rule_engine.htf.types import HTFBias
        from rule_engine.scoring import score_signal as bt_score_signal

        self.bt_processor = BacktesterProcessor(timeframe="1m")
        self.bt_score_signal = bt_score_signal
        self.bt_htf_bias_type = HTFBias

        # Initialize microservices components
        logger.info("Initializing microservices components...")
        from scp_shared.indicators.streaming import (
            StreamingFeatureProcessor as MicroProcessor,
        )
        from scp_shared.rule_engine import score_signal as ms_score_signal
        from scp_shared.rule_engine.htf.types import HTFBias as MSHTFBias

        self.ms_processor = MicroProcessor(timeframe="1m")
        self.ms_score_signal = ms_score_signal
        self.ms_htf_bias_type = MSHTFBias

        # Report
        self.report = DivergenceReport()
        self.report.start_time = datetime.now(UTC)

    def _convert_row_to_backtester_candle(self, row, symbol: str) -> BacktesterCandle:
        """Convert DataFrame row to backtester Candle object.

        Args:
            row: DataFrame row with OHLCV data
            symbol: Symbol name (GC or DXY)

        Returns:
            Backtester Candle object
        """
        return BacktesterCandle(
            timestamp=row.name,  # DataFrame index is timestamp
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            symbol=symbol,
            timeframe="1m",
            source="COMPARISON",
        )

    def _convert_row_to_microservices_candle(
        self, row, symbol: str
    ) -> MicroservicesCandle:
        """Convert DataFrame row to microservices Candle object.

        Args:
            row: DataFrame row with OHLCV data
            symbol: Symbol name (GC or DXY)

        Returns:
            Microservices Candle object
        """
        return MicroservicesCandle(
            timestamp=row.name,  # DataFrame index is timestamp
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
            symbol=symbol,
            timeframe="1m",
            source="COMPARISON",
        )

    def run(self) -> DivergenceReport:
        """Run side-by-side comparison.

        Returns:
            DivergenceReport with all divergences found
        """
        logger.info("=" * 80)
        logger.info(f"Side-by-Side Replay: {self.start.date()} to {self.end.date()}")
        logger.info("=" * 80)

        # Iterate bar-by-bar
        total_bars = len(self.gc_df)
        self.report.total_bars = total_bars

        logger.info(f"Processing {total_bars} bars...")

        # Create mock HTF bias for testing
        # In production, this would come from HTF processor
        # For now, use neutral bias
        mock_htf_bias_bt = self.bt_htf_bias_type(
            bias="neutral",
            direction="neutral",
            score=5.0,
            confidence="low",
            structure_15m=None,
            structure_1h=None,
            dxy_alignment=False,
            chop_detected=False,
        )

        mock_htf_bias_ms = self.ms_htf_bias_type(
            bias="neutral",
            direction="neutral",
            score=5.0,
            confidence="low",
            structure_15m=None,
            structure_1h=None,
            dxy_alignment=False,
            chop_detected=False,
        )

        for bar_idx in range(total_bars):
            if bar_idx % 100 == 0 and bar_idx > 0:
                logger.info(f"  Processed {bar_idx}/{total_bars} bars...")

            # Get current candles
            gc_row = self.gc_df.iloc[bar_idx]
            dxy_row = self.dxy_df.iloc[bar_idx]

            # Create separate candle objects for each implementation (different types)
            bt_gc_candle = self._convert_row_to_backtester_candle(gc_row, "GC")
            bt_dxy_candle = self._convert_row_to_backtester_candle(dxy_row, "DXY")

            ms_gc_candle = self._convert_row_to_microservices_candle(gc_row, "GC")
            ms_dxy_candle = self._convert_row_to_microservices_candle(dxy_row, "DXY")

            # === STAGE 1: Compare Features ===
            bt_features = self.bt_processor.update(bt_gc_candle, bt_dxy_candle)
            ms_features = self.ms_processor.update(ms_gc_candle, ms_dxy_candle)

            # Add required metadata fields for score_signal (if not present)
            # These fields are needed by scoring but not produced by
            # streaming processors
            if "symbol" not in bt_features.index:
                bt_features["symbol"] = "GC"
            if "timeframe" not in bt_features.index:
                bt_features["timeframe"] = "1m"

            if "symbol" not in ms_features.index:
                ms_features["symbol"] = "GC"
            if "timeframe" not in ms_features.index:
                ms_features["timeframe"] = "1m"

            feature_comparison = compare_features(bt_features, ms_features)

            if not feature_comparison.matches:
                # Log first differing feature
                first_diff_field = list(feature_comparison.differences.keys())[0]
                bt_val, ms_val = feature_comparison.differences[first_diff_field]

                # Calculate delta if numeric
                delta = None
                try:
                    delta = float(ms_val) - float(bt_val)
                except (TypeError, ValueError):
                    pass

                self.report.add_divergence(
                    bar_index=bar_idx,
                    timestamp=bt_gc_candle.timestamp,
                    stage="features",
                    component=first_diff_field,
                    backtester_value=bt_val,
                    microservices_value=ms_val,
                    delta=delta,
                    context={
                        "total_feature_diffs": len(feature_comparison.differences),
                        "all_diffs": {
                            k: (v[0], v[1])
                            for k, v in list(feature_comparison.differences.items())[
                                :10
                            ]
                        },
                    },
                )

                if self.stop_on_first:
                    logger.warning("Stopping on first divergence (--stop-on-first)")
                    self.report.stopped_early = True
                    break

            # === STAGE 2: Compare Signals ===
            # Only compare signals if features match
            # (or we're continuing despite divergence)
            if feature_comparison.matches or not self.stop_on_first:
                try:
                    # Generate signals
                    scoring_context = {"session_ok": True, "enforcer_tier": "EarlyMild"}

                    bt_signal = self.bt_score_signal(
                        bt_features, mock_htf_bias_bt, scoring_context
                    )
                    ms_signal = self.ms_score_signal(
                        ms_features, mock_htf_bias_ms, scoring_context
                    )

                    # Only compare if both generated A+ signals
                    # (main divergence of interest)
                    if bt_signal.confidence == "A+" or ms_signal.confidence == "A+":
                        signal_comparison = compare_signals(
                            bt_signal if bt_signal.confidence == "A+" else None,
                            ms_signal if ms_signal.confidence == "A+" else None,
                        )

                        if not signal_comparison.matches:
                            # Signal divergence
                            first_diff_field = (
                                list(signal_comparison.field_diffs.keys())[0]
                                if signal_comparison.field_diffs
                                else "signal_generated"
                            )
                            bt_val, ms_val = signal_comparison.field_diffs.get(
                                first_diff_field,
                                (bt_signal is not None, ms_signal is not None),
                            )

                            # Safe attribute extraction
                            def safe_get_attrs(signal, attrs):
                                """Safely get attributes from signal.

                                Returns None if not found.
                                """
                                result = {}
                                for attr in attrs:
                                    try:
                                        result[attr] = getattr(signal, attr, None)
                                    except (AttributeError, KeyError):
                                        result[attr] = None
                                return result

                            bt_attrs = (
                                safe_get_attrs(
                                    bt_signal, ["setup_type", "score", "confidence"]
                                )
                                if bt_signal
                                else {}
                            )
                            ms_attrs = (
                                safe_get_attrs(
                                    ms_signal, ["setup_type", "score", "confidence"]
                                )
                                if ms_signal
                                else {}
                            )

                            self.report.add_divergence(
                                bar_index=bar_idx,
                                timestamp=bt_gc_candle.timestamp,
                                stage="scoring",
                                component=first_diff_field,
                                backtester_value=bt_val,
                                microservices_value=ms_val,
                                context={
                                    "bt_signal": bt_attrs,
                                    "ms_signal": ms_attrs,
                                },
                            )

                            if self.stop_on_first:
                                logger.warning("Stopping on first signal divergence")
                                self.report.stopped_early = True
                                break

                except Exception as e:
                    logger.warning(
                        f"Error comparing signals at bar {bar_idx}: {e}", exc_info=True
                    )

        self.report.end_time = datetime.now(UTC)

        logger.info("=" * 80)
        logger.info("Comparison complete")
        logger.info("=" * 80)

        return self.report


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Side-by-side comparison of backtester and microservices"
    )

    # Date specification
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        "--date",
        type=str,
        help="Single date to compare (YYYY-MM-DD)",
    )
    date_group.add_argument(
        "--start",
        type=str,
        help="Start date (YYYY-MM-DD), requires --end",
    )

    parser.add_argument(
        "--end",
        type=str,
        help="End date (YYYY-MM-DD), requires --start",
    )

    # Options
    parser.add_argument(
        "--stop-on-first",
        action="store_true",
        help="Stop on first divergence (default: continue through all bars)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for divergence report "
        "(default: output/divergence_<date>.json)",
    )

    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/gc_dx_ohlcv",
        help="Historical data directory (default: data/gc_dx_ohlcv)",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Setup logging
    project_root = Path(__file__).parent.parent
    config = load_config(project_root / "config" / "core.yaml")

    # Adjust log level if verbose
    if args.verbose:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)

    setup_logging(config.system)

    # Parse dates
    if args.date:
        start = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=UTC)
        end = start + timedelta(days=1)
        date_str = args.date
    else:
        if not args.end:
            logger.error("--end is required when using --start")
            return 1
        start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC)
        end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC)
        date_str = f"{args.start}_to_{args.end}"

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = Path(f"output/divergence_{date_str}.json")

    try:
        # Run comparison
        replay = SideBySideReplay(
            data_path=args.data_dir,
            start=start,
            end=end,
            stop_on_first_divergence=args.stop_on_first,
        )

        report = replay.run()

        # Print summary
        report.print_summary()

        # Save report
        report.save(output_path)

        # Return exit code based on results
        if report.first_divergence_bar is None:
            logger.info("✓ SUCCESS: No divergences found")
            return 0
        else:
            logger.warning(
                f"✗ DIVERGENCE: First divergence at bar {report.first_divergence_bar}"
            )
            return 1

    except Exception as e:
        logger.error(f"Comparison failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""E2E test for RuleEngine with multi-timeframe HTF bias.

This script loads GC/DXY data across 1h, 15m, and 1m timeframes, computes
proper HTF bias from higher timeframes, scores signals on 1m entries, and
exports comprehensive results to CSV for manual inspection.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from common.logger import get_logger
from data_layer.loader import HistoricalDataLoader
from data_layer.multi_timeframe_helpers import extract_execution_dataframes
from data_layer.multi_timeframe_sync import MultiTimeframeSyncLayer
from feature_engine.integration import process_features
from rule_engine.htf.calculator import (
    compute_htf_bias_multi_timeframe,
    is_london_or_ny_session,
)
from rule_engine.htf.integration import create_htf_bias_func_with_sync_layer
from rule_engine.htf.types import HTFBias
from rule_engine.scoring import score_signal
from rule_engine.validation import validate_signal

logger = get_logger(__name__)


def create_htf_bias_from_context(context: dict) -> HTFBias:
    """Helper to create HTFBias from context dict for e2e script."""
    bias = context.get("htf_bias", "neutral")
    direction = context.get("htf_direction", "neutral")
    score = context.get("htf_score", 6.5)
    
    if score >= 8.0:
        confidence = "high"
    elif score >= 6.0:
        confidence = "medium"
    else:
        confidence = "low"
    
    return HTFBias(
        bias=bias,
        direction=direction,
        score=score,
        confidence=confidence,
        dxy_alignment=context.get("dxy_corr", -0.5) < -0.6,
    )


def parse_iso_datetime(value: str) -> datetime:
    """Parse ISO-8601 datetime strings, defaulting to UTC when tzinfo missing."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="E2E test of RuleEngine scoring with multi-timeframe HTF bias."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/gc_dx_ohlcv"),
        help="Directory containing GC/DX CSV files (default: data/gc_dx_ohlcv).",
    )
    parser.add_argument(
        "--start",
        type=parse_iso_datetime,
        default=datetime(2025, 9, 30, 7, 0, tzinfo=timezone.utc),
        help="Start datetime (ISO-8601, default: 2025-09-30T07:00:00+00:00).",
    )
    parser.add_argument(
        "--end",
        type=parse_iso_datetime,
        default=datetime(2025, 10, 1, 16, 0, tzinfo=timezone.utc),
        help="End datetime (ISO-8601, default: 2025-10-01T16:00:00+00:00).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory for CSV exports (default: output/).",
    )
    parser.add_argument(
        "--enforcer-tier",
        type=str,
        default="Early Mild",
        choices=["Conservative", "Early Mild", "Mild", "Offensive"],
        help="Enforcer tier for validation (default: Early Mild).",
    )
    parser.add_argument(
        "--use-sync-layer",
        action="store_true",
        help="Use MultiTimeframeSyncLayer for efficient data loading and alignment",
    )
    parser.add_argument(
        "--htf-approach",
        type=str,
        choices=["streaming", "vectorized"],
        default="streaming",
        help="HTF feature computation approach when using sync layer (default: streaming)",
    )
    return parser


def align_htf_candle(features_df: pd.DataFrame, timestamp: pd.Timestamp, freq: str) -> pd.Series | None:
    """Find HTF candle that contains the given timestamp.

    Args:
        features_df: DataFrame with ts_event column
        timestamp: Target timestamp
        freq: Pandas frequency string ('1H', '15T')

    Returns:
        Series of HTF features, or None if not found
    """
    # Floor timestamp to HTF boundary
    # Use 'h' for hour and 'min' for minute (modern pandas frequency strings)
    freq_fixed = freq.replace("H", "h").replace("T", "min")
    ts_htf = timestamp.floor(freq_fixed)

    # Find matching candle
    matches = features_df[features_df["ts_event"] == ts_htf]
    if len(matches) == 0:
        return None

    return matches.iloc[0]


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 80)
    logger.info("E2E RuleEngine Test: Multi-Timeframe HTF Bias")
    logger.info("=" * 80)
    if args.use_sync_layer:
        logger.info("Using MultiTimeframeSyncLayer for data loading")
    logger.info("=" * 80)

    # === STEP 1: Load data for all timeframes ===
    logger.info(f"Loading data from {args.data_dir}")
    logger.info(f"Date range: {args.start} to {args.end}")

    if args.use_sync_layer:
        # New approach: Use MultiTimeframeSyncLayer
        logger.info("\nLoading multi-timeframe data with sync layer...")
        try:
            sync_layer = MultiTimeframeSyncLayer(str(args.data_dir))
            multi_tf_data = sync_layer.load(args.start, args.end)
            
            logger.info(
                f"  Loaded {len(multi_tf_data)} synchronized bars "
                f"from {multi_tf_data.execution_timestamps[0]} "
                f"to {multi_tf_data.execution_timestamps[-1]}"
            )
            
            # Extract 1m DataFrames for processing
            data_1m_gc, data_1m_dxy = extract_execution_dataframes(multi_tf_data)
            data_1m = {"GC": data_1m_gc, "DXY": data_1m_dxy}
            
            logger.info(f"  GC 1m: {len(data_1m['GC'])} candles")
            logger.info(f"  DXY 1m: {len(data_1m['DXY'])} candles")
            
            # For HTF data, we'll use the sync layer's HTF bias function
            # which handles feature computation internally
            use_sync_htf = True
            has_15m = True  # Assume available if sync layer loaded successfully
            
        except Exception as e:
            logger.error(f"Failed to load with sync layer: {e}", exc_info=True)
            logger.info("Falling back to manual loading...")
            args.use_sync_layer = False
            use_sync_htf = False
    
    if not args.use_sync_layer:
        # Old approach: Manual loading (keep for comparison)
        loader = HistoricalDataLoader(args.data_dir)
        symbols = ["GC", "DXY"]

        logger.info("\nLoading 1h data...")
        data_1h = loader.load(symbols, "1h", args.start, args.end)
        logger.info(f"  GC 1h: {len(data_1h['GC'])} candles")
        logger.info(f"  DXY 1h: {len(data_1h['DXY'])} candles")

        logger.info("\nLoading 15m data...")
        try:
            data_15m = loader.load(symbols, "15m", args.start, args.end)
            logger.info(f"  GC 15m: {len(data_15m['GC'])} candles")
            logger.info(f"  DXY 15m: {len(data_15m['DXY'])} candles")
            has_15m = len(data_15m['GC']) > 0 and len(data_15m['DXY']) > 0
        except Exception as e:
            logger.warning(f"  Failed to load 15m data: {e}")
            data_15m = None
            has_15m = False

        logger.info("\nLoading 1m data...")
        data_1m = loader.load(symbols, "1m", args.start, args.end)
        logger.info(f"  GC 1m: {len(data_1m['GC'])} candles")
        logger.info(f"  DXY 1m: {len(data_1m['DXY'])} candles")
        use_sync_htf = False

    # === STEP 2: Process features for each timeframe ===
    logger.info("\n" + "=" * 80)
    logger.info("Processing features for each timeframe...")

    if use_sync_htf:
        # When using sync layer, HTF features are computed internally
        # We only need to process 1m features for signal scoring
        logger.info("\nProcessing 1m features...")
        features_1m = process_features(
            data_1m["GC"],
            data_1m["DXY"],
            "1m",
        )
        logger.info(f"  Generated {len(features_1m)} feature rows")
        
        # Create HTF bias function with sync layer
        htf_bias_func = create_htf_bias_func_with_sync_layer(
            multi_tf_data,
            approach=args.htf_approach,
        )
        logger.info(f"  Created HTF bias function (approach: {args.htf_approach})")
        
        # Placeholders for compatibility with rest of script
        features_1h = None
        features_15m = None
    else:
        # Old approach: Process all timeframes separately
        logger.info("\nProcessing 1h features...")
        features_1h = process_features(
            data_1h["GC"],
            data_1h["DXY"],
            "1h",
        )
        logger.info(f"  Generated {len(features_1h)} feature rows")

        if has_15m:
            logger.info("\nProcessing 15m features...")
            try:
                features_15m = process_features(
                    data_15m["GC"],
                    data_15m["DXY"],
                    "15m",
                )
                logger.info(f"  Generated {len(features_15m)} feature rows")
            except Exception as e:
                logger.warning(f"  Failed to process 15m features: {e}")
                features_15m = None
                has_15m = False
        else:
            logger.warning("  Skipping 15m processing (no data)")
            features_15m = None

        logger.info("\nProcessing 1m features...")
        features_1m = process_features(
            data_1m["GC"],
            data_1m["DXY"],
            "1m",
        )
        logger.info(f"  Generated {len(features_1m)} feature rows")
        htf_bias_func = None

    # === STEP 3: Export feature CSVs ===
    logger.info("\n" + "=" * 80)
    logger.info("Exporting feature CSVs...")

    if features_1h is not None:
        features_1h.to_csv(args.output_dir / "e2e_features_1h.csv", index=False)
        logger.info(f"  Saved: {args.output_dir / 'e2e_features_1h.csv'}")
    else:
        logger.info("  Skipped 1h export (using sync layer)")

    if has_15m and features_15m is not None:
        features_15m.to_csv(args.output_dir / "e2e_features_15m.csv", index=False)
        logger.info(f"  Saved: {args.output_dir / 'e2e_features_15m.csv'}")
    else:
        logger.info("  Skipped 15m export (using sync layer or no data)")

    features_1m.to_csv(args.output_dir / "e2e_features_1m.csv", index=False)
    logger.info(f"  Saved: {args.output_dir / 'e2e_features_1m.csv'}")

    # === STEP 4: Score signals on 1m with HTF bias ===
    logger.info("\n" + "=" * 80)
    logger.info("Scoring signals with HTF bias...")

    signals_data = []
    htf_bias_log = []
    skipped_no_htf = 0

    for idx, row_1m in features_1m.iterrows():
        ts = row_1m["ts_event"]

        # Skip if essential features are missing
        if pd.isna(row_1m.get("vwap")) or pd.isna(row_1m.get("rsi")):
            continue

        # Compute HTF bias
        if use_sync_htf:
            # Use sync layer HTF bias function
            try:
                # Ensure row_1m has "timestamp" key (HTF bias function expects it)
                # Features DataFrame uses "ts_event" but HTF function expects "timestamp"
                row_1m_for_htf = row_1m.copy()
                if "timestamp" not in row_1m_for_htf and "ts_event" in row_1m_for_htf:
                    row_1m_for_htf["timestamp"] = row_1m_for_htf["ts_event"]
                
                # Build context dict for HTF bias function
                validation_context = {
                    "session_ok": is_london_or_ny_session(ts),
                }
                htf_bias_obj = htf_bias_func(row_1m_for_htf, validation_context)
                htf_bias = htf_bias_obj.bias
                htf_direction = htf_bias_obj.direction
                htf_score = htf_bias_obj.score
                
                # For logging, extract structure info if available
                row_1h = None  # Not used with sync layer
                row_15m = None  # Not used with sync layer
            except Exception as e:
                logger.warning(f"Failed to compute HTF bias with sync layer at {ts}: {e}")
                skipped_no_htf += 1
                continue
        else:
            # Old approach: Manual alignment
            # Align with 1h candle
            row_1h = align_htf_candle(features_1h, ts, "1H")
            if row_1h is None:
                skipped_no_htf += 1
                continue

            # Align with 15m candle (if available)
            if has_15m and features_15m is not None:
                row_15m = align_htf_candle(features_15m, ts, "15T")
                if row_15m is None:
                    # Use 1h as fallback for 15m
                    row_15m = row_1h
            else:
                # Use 1h for both if 15m not available
                row_15m = row_1h

            # Compute HTF bias from 1h + 15m (or 1h + 1h if 15m unavailable)
            htf_bias, htf_direction, htf_score = compute_htf_bias_multi_timeframe(
                row_1h, row_15m
            )
            htf_bias_obj = None

        # Log HTF bias for this candle
        if use_sync_htf and htf_bias_obj:
            htf_bias_log.append({
                "timestamp": ts,
                "htf_bias": htf_bias,
                "htf_direction": htf_direction,
                "htf_score": htf_score,
                "structure_1h": htf_bias_obj.structure_1h or "",
                "structure_15m": htf_bias_obj.structure_15m or "",
                "dxy_corr_1h": htf_bias_obj.dxy_corr_1h,
                "dxy_corr_15m": htf_bias_obj.dxy_corr_15m,
            })
        else:
            htf_bias_log.append({
                "timestamp": ts,
                "htf_bias": htf_bias,
                "htf_direction": htf_direction,
                "htf_score": htf_score,
                "structure_1h": row_1h.get("structure_label", "") if row_1h is not None else "",
                "structure_15m": row_15m.get("structure_label", "") if row_15m is not None else "",
                "dxy_corr_1h": row_1h.get("dxy_corr") if row_1h is not None else None,
                "dxy_corr_15m": row_15m.get("dxy_corr") if row_15m is not None else None,
            })

        # Build context
        session_ok = is_london_or_ny_session(ts)
        
        # Get DXY correlation from appropriate source
        if use_sync_htf and htf_bias_obj:
            # Use DXY correlation from HTF bias object when using sync layer
            dxy_corr_1h = htf_bias_obj.dxy_corr_1h
        elif row_1h is not None:
            # Use DXY correlation from 1h features when available
            dxy_corr_1h = row_1h.get("dxy_corr")
        else:
            # Fallback to 1m DXY correlation if no HTF data available
            dxy_corr_1h = row_1m.get("dxy_corr")
        
        dxy_trending_clean = (
            dxy_corr_1h is not None
            and not pd.isna(dxy_corr_1h)
            and dxy_corr_1h < -0.6
        )

        context = {
            "htf_bias": htf_bias,
            "htf_direction": htf_direction,
            "htf_score": htf_score,
            "session_ok": session_ok,
            "enforcer_tier": args.enforcer_tier,
            "dxy_trending_clean": dxy_trending_clean,
            "fatigue_flag": False,
            "risk_allowed": True,
            "news_ok": True,
            "ceo_directive_active": True,
            "buffer_phase": "5-15k",
            "dxy_corr": row_1m.get("dxy_corr"),
        }

        # Score signal
        try:
            # Ensure required fields exist for signal
            row_1m_for_scoring = row_1m.copy()
            if "timestamp" not in row_1m_for_scoring and "ts_event" in row_1m_for_scoring:
                row_1m_for_scoring["timestamp"] = row_1m_for_scoring["ts_event"]
            if "timeframe" not in row_1m_for_scoring:
                row_1m_for_scoring["timeframe"] = "1m"
            if "symbol" not in row_1m_for_scoring:
                row_1m_for_scoring["symbol"] = row_1m_for_scoring.get("symbol", "GC")
            
            if not use_sync_htf:
                htf_bias_obj = create_htf_bias_from_context(context)
            # else: htf_bias_obj already computed above
            signal = score_signal(row_1m_for_scoring, htf_bias_obj, context)

            # Validate signal
            validated = validate_signal(signal, htf_bias_obj, context)

            # Collect signal data (use validated signal, not original)
            signals_data.append({
                "timestamp": ts,
                "symbol": validated.symbol,
                "timeframe": validated.timeframe,
                "direction": validated.direction,
                "setup_type": validated.setup_type,
                "score": validated.score,
                "confidence": validated.confidence,
                "htf_bias": htf_bias,
                "htf_direction": htf_direction,
                "htf_score": htf_score,
                "session_ok": session_ok,
                "enforcer_tier": validated.enforcer_tier,
                # Factor scores
                **validated.factors,
                # Validation flags
                **{f"valid_{k}": v for k, v in validated.validation_flags.items()},
                # Market data
                "close": row_1m["close"],
                "vwap": row_1m["vwap"],
                "rsi": row_1m.get("rsi"),
                "dxy_corr": row_1m.get("dxy_corr"),
                # Rationale
                "rationale": validated.rationale,
            })

        except Exception as e:
            logger.warning(f"Failed to score signal at {ts}: {e}")
            continue

    logger.info(f"\nProcessed {len(signals_data)} signals")
    logger.info(f"Skipped {skipped_no_htf} candles (no HTF data)")

    # === STEP 5: Export signal CSVs ===
    logger.info("\n" + "=" * 80)
    logger.info("Exporting signal CSVs...")

    if len(signals_data) > 0:
        signals_df = pd.DataFrame(signals_data)

        # Export all signals
        signals_df.to_csv(args.output_dir / "e2e_signals_all.csv", index=False)
        logger.info(f"  Saved: {args.output_dir / 'e2e_signals_all.csv'}")

        # Export A+ signals only
        aplus_df = signals_df[signals_df["confidence"] == "A+"]
        aplus_df.to_csv(args.output_dir / "e2e_signals_aplus.csv", index=False)
        logger.info(f"  Saved: {args.output_dir / 'e2e_signals_aplus.csv'} ({len(aplus_df)} A+ signals)")

        # Export HTF bias log
        htf_bias_df = pd.DataFrame(htf_bias_log)
        htf_bias_df.to_csv(args.output_dir / "e2e_htf_bias_log.csv", index=False)
        logger.info(f"  Saved: {args.output_dir / 'e2e_htf_bias_log.csv'}")

        # === STEP 6: Summary statistics ===
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY STATISTICS")
        logger.info("=" * 80)

        logger.info(f"\nCandles Processed:")
        if features_1h is not None:
            logger.info(f"  1h:  {len(features_1h):,} candles")
        else:
            logger.info(f"  1h:  N/A (using sync layer)")
        if has_15m and features_15m is not None:
            logger.info(f"  15m: {len(features_15m):,} candles")
        else:
            logger.info(f"  15m: N/A (using sync layer or no data)")
        logger.info(f"  1m:  {len(features_1m):,} candles")
        logger.info(f"  Signals generated: {len(signals_df):,}")

        # HTF Bias Distribution
        logger.info(f"\nHTF Bias Distribution:")
        bias_counts = htf_bias_df["htf_bias"].value_counts()
        total = len(htf_bias_df)
        for bias, count in bias_counts.items():
            pct = (count / total) * 100
            logger.info(f"  {bias:8s}: {count:4d} ({pct:5.1f}%)")

        # Signal Confidence Distribution
        logger.info(f"\nSignal Confidence Distribution:")
        conf_counts = signals_df["confidence"].value_counts()
        for conf, count in conf_counts.items():
            pct = (count / len(signals_df)) * 100
            logger.info(f"  {conf:7s}: {count:4d} ({pct:5.1f}%)")

        # Setup Type Distribution
        logger.info(f"\nSetup Type Distribution:")
        setup_counts = signals_df["setup_type"].value_counts()
        for setup, count in setup_counts.items():
            pct = (count / len(signals_df)) * 100
            logger.info(f"  {setup:20s}: {count:4d} ({pct:5.1f}%)")

        # Average Score by Setup Type
        logger.info(f"\nAverage Score by Setup Type:")
        avg_scores = signals_df.groupby("setup_type")["score"].mean()
        for setup, avg_score in avg_scores.items():
            logger.info(f"  {setup:20s}: {avg_score:5.2f}")

        # Average Score by Confidence
        logger.info(f"\nAverage Score by Confidence:")
        avg_by_conf = signals_df.groupby("confidence")["score"].mean()
        for conf, avg_score in avg_by_conf.items():
            logger.info(f"  {conf:7s}: {avg_score:5.2f}")

        # Top 10 Highest Scoring Signals
        logger.info(f"\nTop 10 Highest Scoring Signals:")
        top_signals = signals_df.nlargest(10, "score")[
            ["timestamp", "setup_type", "score", "confidence", "htf_bias", "htf_score"]
        ]
        for _, sig in top_signals.iterrows():
            logger.info(
                f"  {sig['timestamp']} | {sig['setup_type']:20s} | "
                f"Score: {sig['score']:4.1f} | {sig['confidence']:7s} | "
                f"HTF: {sig['htf_bias']:8s} ({sig['htf_score']:.1f})"
            )

        logger.info("\n" + "=" * 80)
        logger.info("E2E Test Complete!")
        logger.info("=" * 80)

    else:
        logger.error("No signals generated! Check data alignment and features.")


if __name__ == "__main__":
    main()


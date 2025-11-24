"""Feature Engine Integration Layer.

This module provides the integration layer that combines HistoricalDataLoader
output with FeatureEngine aggregator, adds structure labels and VWAP deviations,
and integrates validation rules to produce complete feature DataFrames ready
for Rule Engine scoring.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd

from common.logger import get_logger
from feature_engine.aggregator import aggregate_features
from feature_engine.structure import calculate_structure_labels
from feature_engine.vwap import calculate_vwap_deviation
from rule_engine.htf.types import HTFBias
from rule_engine.scoring import score_signal
from rule_engine.signal_logger import log_signal
from rule_engine.validation import validate_signal_with_sop

if TYPE_CHECKING:
    from rule_engine.signal import Signal
    from validation.engine import ValidationEngine, ValidationResult
    from validation.guardrails import GuardrailResult
    from validation.schema import ValidationContext
    from validation.session_validator import SessionConstraints, SessionValidator

logger = get_logger(__name__)


def prepare_for_aggregation(df: pd.DataFrame) -> pd.DataFrame:
    """Convert DataFrame from timestamp index format to ts_event column format.

    HistoricalDataLoader returns DataFrames with timestamp as index, but
    aggregate_features() expects ts_event as a column. This function handles
    the conversion.

    Args:
        df: DataFrame with timestamp index (DatetimeIndex).

    Returns:
        DataFrame with ts_event column and RangeIndex, preserving all other columns.

    Raises:
        ValueError: If DataFrame doesn't have a DatetimeIndex.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(
            f"Expected DataFrame with DatetimeIndex, got {type(df.index)}"
        )

    # Create a copy to avoid modifying the original
    result = df.copy()

    # Convert index to column
    result["ts_event"] = result.index

    # Reset index to RangeIndex
    result = result.reset_index(drop=True)

    return result


def align_dataframes(
    gc_df: pd.DataFrame, dxy_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Align GC and DXY DataFrames by timestamp for correlation calculation.

    Performs inner join on timestamps to ensure both DataFrames have matching
    timestamps for correlation calculation. Works with both timestamp index
    and ts_event column formats.

    Args:
        gc_df: GC DataFrame (with timestamp index or ts_event column).
        dxy_df: DXY DataFrame (with timestamp index or ts_event column).

    Returns:
        Tuple of (aligned_gc_df, aligned_dxy_df) with matching timestamps.

    Raises:
        ValueError: If no overlapping timestamps found.
    """
    # Convert to common format: both with ts_event column
    if isinstance(gc_df.index, pd.DatetimeIndex) and "ts_event" not in gc_df.columns:
        gc_work = prepare_for_aggregation(gc_df)
    elif "ts_event" in gc_df.columns:
        gc_work = gc_df.copy()
    else:
        raise ValueError(
            "GC DataFrame must have either DatetimeIndex or ts_event column"
        )

    if isinstance(dxy_df.index, pd.DatetimeIndex) and "ts_event" not in dxy_df.columns:
        dxy_work = prepare_for_aggregation(dxy_df)
    elif "ts_event" in dxy_df.columns:
        dxy_work = dxy_df.copy()
    else:
        raise ValueError(
            "DXY DataFrame must have either DatetimeIndex or ts_event column"
        )

    # Find overlapping timestamps
    gc_timestamps = set(gc_work["ts_event"])
    dxy_timestamps = set(dxy_work["ts_event"])
    common_timestamps = gc_timestamps.intersection(dxy_timestamps)

    if len(common_timestamps) == 0:
        raise ValueError("No overlapping timestamps found between GC and DXY DataFrames")

    # Filter to common timestamps
    gc_result = gc_work[gc_work["ts_event"].isin(common_timestamps)].copy()
    dxy_result = dxy_work[dxy_work["ts_event"].isin(common_timestamps)].copy()

    # Sort by timestamp to ensure consistent ordering
    gc_result = gc_result.sort_values("ts_event").reset_index(drop=True)
    dxy_result = dxy_result.sort_values("ts_event").reset_index(drop=True)

    logger.info(
        f"Aligned GC and DXY DataFrames: {len(gc_result)} matching timestamps"
    )

    return gc_result, dxy_result


def process_features(
    gc_df: pd.DataFrame,
    dxy_df: pd.DataFrame,
    timeframe: str,
    context: dict | None = None,
    validation_engine: ValidationEngine | None = None,
    session_validator: SessionValidator | None = None,
) -> pd.DataFrame:
    """Process aligned GC and DXY datasets through full FeatureEngine pipeline.

    This is the main integration function that:
    1. Converts loader DataFrames to aggregator format
    2. Aligns GC and DXY data
    3. Computes all indicators (RSI, VWAP, EMA, DXY correlation)
    4. Adds structure labels (HH/HL/LH/LL)
    5. Adds VWAP deviation column
    6. Applies validation rules
    7. Returns complete feature DataFrame ready for scoring

    Args:
        gc_df: GC DataFrame from HistoricalDataLoader (timestamp index, OHLCV columns).
        dxy_df: DXY DataFrame from HistoricalDataLoader (timestamp index, OHLCV columns).
        timeframe: Timeframe string (e.g., "1m", "15m", "1h").
        context: Optional validation context dict with keys:
                 - session_ok: bool
                 - tier_active: str
                 - htf_bias: str
                 - dxy_trending_clean: bool
                 - fatigue_flag: bool
                 - risk_allowed: bool
                 - news_ok: bool
                 - ceo_directive_active: bool
                 - buffer_phase: str
        validation_engine: Optional ValidationEngine instance for trade validation.
        session_validator: Optional SessionValidator instance for session validation.

    Returns:
        Complete feature DataFrame with all indicators, structure labels, and
        VWAP deviation. Ready for Rule Engine scoring.

    Raises:
        ValueError: If required columns are missing or alignment fails.
        TypeError: If inputs are not DataFrames.

    Example:
        >>> from data_layer import HistoricalDataLoader
        >>> from feature_engine.integration import process_features
        >>> from datetime import datetime, timezone
        >>>
        >>> loader = HistoricalDataLoader("data/gc_dx_ohlcv")
        >>> start = datetime(2025, 9, 30, 4, 20, 0, tzinfo=timezone.utc)
        >>> end = datetime(2025, 9, 30, 5, 0, 0, tzinfo=timezone.utc)
        >>> data = loader.load(["GC", "DXY"], "1m", start, end)
        >>>
        >>> features = process_features(
        ...     data["GC"],
        ...     data["DXY"],
        ...     "1m",
        ...     context={"session_ok": True, ...}
        ... )
    """
    # Validate inputs
    if not isinstance(gc_df, pd.DataFrame):
        raise TypeError("gc_df must be a pandas DataFrame")
    if not isinstance(dxy_df, pd.DataFrame):
        raise TypeError("dxy_df must be a pandas DataFrame")

    # Validate required columns
    required_gc_cols = ["open", "high", "low", "close", "volume"]
    missing_cols = [col for col in required_gc_cols if col not in gc_df.columns]
    if missing_cols:
        raise ValueError(
            f"GC DataFrame missing required columns: {missing_cols}"
        )

    # Align DataFrames by timestamp (returns DataFrames with ts_event column)
    gc_for_agg, dxy_for_agg = align_dataframes(gc_df, dxy_df)

    # Run aggregate_features to compute all indicators
    logger.info(f"Computing indicators for {len(gc_for_agg)} rows")
    features = aggregate_features(gc_for_agg, dxy_for_agg, timeframe)

    # Add structure labels
    logger.info("Computing structure labels")
    structure_labels = calculate_structure_labels(features)
    features["structure_label"] = structure_labels

    # Add VWAP deviation (requires VWAP to be computed first)
    if "vwap" in features.columns:
        logger.info("Computing VWAP deviation")
        vwap_deviation = calculate_vwap_deviation(features)
        features["vwap_deviation"] = vwap_deviation
    else:
        logger.warning("VWAP not computed, skipping VWAP deviation")

    # Ensure no NaNs past initialization window
    # RSI needs 14 periods, EMA needs 50, DXY correlation needs 50
    max_init_window = 50  # Maximum initialization window
    if len(features) > max_init_window:
        # Check for NaNs in feature columns past initialization window
        feature_cols = [
            "vwap",
            "rsi",
            "ema_9",
            "ema_20",
            "ema_50",
            "dxy_corr",
            "vwap_deviation",
        ]
        for col in feature_cols:
            if col in features.columns:
                nan_count = features[col].iloc[max_init_window:].isna().sum()
                if nan_count > 0:
                    logger.warning(
                        f"Found {nan_count} NaN values in {col} past initialization window"
                    )

    # Apply validation if context and validators provided
    if context and (validation_engine or session_validator):
        logger.info("Applying validation rules")
        features = _apply_validation(
            features, context, validation_engine, session_validator
        )

    logger.info(
        f"Feature processing complete: {len(features)} rows, "
        f"{len(features.columns)} columns"
    )

    return features


def _apply_validation(
    features: pd.DataFrame,
    context: dict,
    validation_engine: ValidationEngine | None,
    session_validator: SessionValidator | None,
) -> pd.DataFrame:
    """Apply validation rules to feature DataFrame.

    Args:
        features: Feature DataFrame with ts_event column.
        context: Validation context dict.
        validation_engine: Optional ValidationEngine instance.
        session_validator: Optional SessionValidator instance.

    Returns:
        Feature DataFrame with validation_status column added.
    """
    # Add validation_status column
    features["validation_status"] = "unknown"

    if session_validator and "ts_event" in features.columns:
        # Apply session validation for each timestamp
        for idx, row in features.iterrows():
            timestamp = row["ts_event"]
            if isinstance(timestamp, datetime):
                session_result = session_validator.evaluate(timestamp)
                if session_result.session_ok:
                    features.loc[idx, "validation_status"] = "session_ok"
                else:
                    features.loc[idx, "validation_status"] = "session_blocked"
            else:
                logger.warning(f"Invalid timestamp at index {idx}: {timestamp}")

    # Note: Full ValidationEngine validation would require trade direction,
    # which is determined during scoring. We mark rows as ready for validation.
    if validation_engine:
        features["validation_ready"] = True

    return features


def process_features_with_validation(
    features: pd.Series,
    htf_bias: HTFBias,
    market_state: dict,
    session_constraints: SessionConstraints,
    guardrail_result: GuardrailResult | None = None,
    log_signals: bool = False,
    log_dir: str | None = None,
) -> Signal:
    """Process a single feature row through scoring and validation.

    This function integrates:
    1. Feature-to-Signal scoring (RuleEngine)
    2. SOP validation (ValidationEngine + SessionValidator + Guardrails)
    3. Optional signal logging

    Args:
        features: Feature series for a single timestamp
        htf_bias: HTFBias object containing HTF analysis
        market_state: Market context dict with:
            - buffer_phase: Current capital buffer phase
            - tier_active: Active enforcer tier
            - ceo_directive_active: CEO directive status
            - news_ok: News event status
            - session_ok: Session validity
        session_constraints: SessionConstraints from SessionValidator
        guardrail_result: Optional GuardrailResult from BehaviorGuardrails
        log_signals: Whether to log signals to disk
        log_dir: Directory for signal logs (required if log_signals=True)

    Returns:
        Validated Signal object with full SOP compliance

    Example:
        >>> from feature_engine.backtesting import BacktestProcessor
        >>> from rule_engine.htf.calculator import compute_htf_bias
        >>> processor = BacktestProcessor("1m")
        >>> for features, validation_context in processor.iterate_with_context(gc_df, dxy_df):
        ...     # Compute HTF bias first
        ...     htf_bias = compute_htf_bias(features_1h, features_15m, dxy_1h, df_15m)
        ...     market_state = {"tier_active": "EarlyMild", ...}
        ...     signal = process_features_with_validation(
        ...         features,
        ...         htf_bias,
        ...         market_state,
        ...         validation_context["session_constraints"],
        ...         validation_context.get("guardrail_result")
        ...     )
        ...     if signal.confidence == "A+":
        ...         # Execute trade
        ...         pass
    """
    # Step 1: Build scoring context (minimal, most data now in HTFBias)
    scoring_context = {
        "session_ok": market_state.get("session_ok", True),
        "enforcer_tier": market_state.get("tier_active", "Conservative"),
    }

    # Step 2: Score the signal with HTFBias
    signal = score_signal(features, htf_bias, scoring_context)

    # Step 3: Apply full SOP validation
    validated_signal = validate_signal_with_sop(
        signal=signal,
        features=features,
        market_state=market_state,
        session_constraints=session_constraints,
        guardrail_result=guardrail_result,
        htf_bias=htf_bias,
    )

    # Step 4: Log signal if requested
    if log_signals and log_dir:
        log_signal(validated_signal, log_dir=log_dir)

    return validated_signal


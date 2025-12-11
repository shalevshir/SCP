"""HTF Feature Computation for Multi-Timeframe Sync Layer.

This module provides both streaming (incremental) and vectorized (batch)
approaches for computing HTF features from synchronized multi-timeframe data.

Streaming approach: Maintains state and updates incrementally as new HTF bars arrive.
Vectorized approach: Pre-computes all HTF features at once for efficiency.
"""


import pandas as pd
from common.logger import get_logger
from common.types import Candle
from data_layer.multi_timeframe_helpers import (
    candles_to_dataframe,
    extract_htf_candles_by_timeframe,
)
from data_layer.multi_timeframe_sync import MultiTimeframeData, SynchronizedBar
from feature_engine.aggregator import aggregate_features
from feature_engine.streaming import StreamingFeatureProcessor
from feature_engine.structure import calculate_structure_labels
from feature_engine.vwap import calculate_vwap_deviation

logger = get_logger(__name__)


class StreamingHTFFeatureComputer:
    """Maintains state for incremental HTF feature computation.

    Uses StreamingFeatureProcessor internally for 1h and 15m timeframes.
    Updates features as new HTF bars arrive from MultiTimeframeData.

    This approach is efficient for live trading where HTF bars arrive
    incrementally and we want to maintain state between updates.

    Attributes:
        processor_1h: Streaming feature processor for 1H timeframe
        processor_15m: Streaming feature processor for 15M timeframe
        features_1h: Most recent 1H features (pd.Series)
        features_15m: Most recent 15M features (pd.Series)
        last_1h_timestamp: Last 1H bar timestamp processed
        last_15m_timestamp: Last 15M bar timestamp processed
    """

    def __init__(
        self,
        rsi_period: int = 14,
        ema_periods: list[int] | None = None,
        dxy_window: int = 50,
        swing_window: int | None = None,
    ) -> None:
        """Initialize streaming HTF feature computer.

        Args:
            rsi_period: RSI calculation period (default: 14)
            ema_periods: List of EMA periods (default: [9, 20, 50])
            dxy_window: DXY correlation window for 1m (default: 50)
                       HTF timeframes use scaled-down windows to warm up faster:
                       - 1H: dxy_window // 2 (25 bars = ~1 day)
                       - 15M: dxy_window // 1.5 (33 bars = ~8 hours)
                       - 5M: dxy_window // 1.25 (40 bars = ~3 hours)
            swing_window: Structure label swing window (default: 5)
        """
        # Scale down dxy_window for HTF to ensure faster warmup
        # 1H: 25 bars = ~1 day of data (vs 50 hours = 2+ days)
        # 15M: 33 bars = ~8 hours (vs 12.5 hours)
        # 5M: 40 bars = ~3 hours (vs 4+ hours)
        dxy_window_1h = max(20, dxy_window // 2)  # Minimum 20 bars
        dxy_window_15m = max(25, int(dxy_window // 1.5))  # Minimum 25 bars
        dxy_window_5m = max(30, int(dxy_window // 1.25))  # Minimum 30 bars
        
        self.processor_1h = StreamingFeatureProcessor(
            timeframe="1h",
            rsi_period=rsi_period,
            ema_periods=ema_periods,
            dxy_window=dxy_window_1h,
            swing_window=swing_window,
        )
        self.processor_15m = StreamingFeatureProcessor(
            timeframe="15m",
            rsi_period=rsi_period,
            ema_periods=ema_periods,
            dxy_window=dxy_window_15m,
            swing_window=swing_window,
        )
        self.processor_5m = StreamingFeatureProcessor(
            timeframe="5m",
            rsi_period=rsi_period,
            ema_periods=ema_periods,
            dxy_window=dxy_window_5m,
            swing_window=swing_window,
        )

        self.features_1h = pd.Series(dtype=object)
        self.features_15m = pd.Series(dtype=object)
        self.features_5m = pd.Series(dtype=object)
        self.last_1h_timestamp: pd.Timestamp | None = None
        self.last_15m_timestamp: pd.Timestamp | None = None
        self.last_5m_timestamp: pd.Timestamp | None = None

        logger.debug("StreamingHTFFeatureComputer initialized")

    def update_from_sync_bar(
        self,
        sync_bar: SynchronizedBar,
        prev_sync_bar: SynchronizedBar | None = None,
    ) -> tuple[pd.Series, pd.Series, pd.Series]:
        """Update HTF features from synchronized bar.

        Only updates when HTF bars change (new bar closed). This prevents
        redundant computation when the same HTF bar is used for multiple
        execution timestamps.

        Args:
            sync_bar: Current synchronized bar
            prev_sync_bar: Previous synchronized bar (optional, for optimization)

        Returns:
            Tuple of (features_5m, features_15m, features_1h) as pd.Series
        """
        # Update 5m features if bar changed
        if sync_bar.htf_5m:
            htf_5m_timestamp = pd.Timestamp(sync_bar.htf_5m[0].timestamp)
            if (
                self.last_5m_timestamp is None
                or htf_5m_timestamp != self.last_5m_timestamp
            ):
                self.features_5m = self.processor_5m.update(
                    sync_bar.htf_5m[0], sync_bar.htf_5m[1]
                )
                self.last_5m_timestamp = htf_5m_timestamp
                logger.debug(
                    f"Updated 5m features at {htf_5m_timestamp} "
                    f"(dxy_structure: {self.features_5m.get('dxy_structure_label', 'N/A')})"
                )

        # Update 15m features if bar changed
        if sync_bar.htf_15m:
            htf_15m_timestamp = pd.Timestamp(sync_bar.htf_15m[0].timestamp)
            if (
                self.last_15m_timestamp is None
                or htf_15m_timestamp != self.last_15m_timestamp
            ):
                self.features_15m = self.processor_15m.update(
                    sync_bar.htf_15m[0], sync_bar.htf_15m[1]
                )
                self.last_15m_timestamp = htf_15m_timestamp
                logger.debug(
                    f"Updated 15m features at {htf_15m_timestamp} "
                    f"(structure: {self.features_15m.get('structure_label', 'N/A')})"
                )

        # Update 1h features if bar changed
        if sync_bar.htf_1h:
            htf_1h_timestamp = pd.Timestamp(sync_bar.htf_1h[0].timestamp)
            if (
                self.last_1h_timestamp is None
                or htf_1h_timestamp != self.last_1h_timestamp
            ):
                self.features_1h = self.processor_1h.update(
                    sync_bar.htf_1h[0], sync_bar.htf_1h[1]
                )
                self.last_1h_timestamp = htf_1h_timestamp
                # Log at INFO level for visibility
                structure_val = self.features_1h.get('structure_label', 'N/A')
                buffer_size = len(self.processor_1h.structure_buffer)
                logger.info(
                    f"Updated 1h features at {htf_1h_timestamp} "
                    f"(structure: {structure_val}, buffer: {buffer_size})"
                )

        return self.features_5m, self.features_15m, self.features_1h

    def is_warmed_up(self) -> bool:
        """Check if all processors have enough data.

        Returns:
            True if all 1h, 15m, and 5m processors are warmed up
        """
        return (
            self.processor_1h.is_warmed_up()
            and self.processor_15m.is_warmed_up()
            and self.processor_5m.is_warmed_up()
        )


def compute_htf_features_vectorized(
    gc_candles_15m: list[Candle],
    dxy_candles_15m: list[Candle],
    gc_candles_1h: list[Candle],
    dxy_candles_1h: list[Candle],
    rsi_period: int = 14,
    ema_periods: list[int] | None = None,
    dxy_window: int = 50,
    swing_window: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Batch compute HTF features for all candles.

    This approach pre-computes all HTF features at once using vectorized
    pandas operations. More efficient for backtesting where all data is
    available upfront.

    Args:
        gc_candles_15m: List of GC 15m candles
        dxy_candles_15m: List of DXY 15m candles
        gc_candles_1h: List of GC 1h candles
        dxy_candles_1h: List of DXY 1h candles
        rsi_period: RSI calculation period (default: 14)
        ema_periods: List of EMA periods (default: [9, 20, 50])
        dxy_window: DXY correlation window for 1m (default: 50)
                   HTF timeframes use scaled-down windows:
                   - 1H: dxy_window // 2 (25 bars = ~1 day)
                   - 15M: dxy_window // 1.5 (33 bars = ~8 hours)
        swing_window: Structure label swing window (default: 5)

    Returns:
        Tuple of (features_15m_df, features_1h_df) with all computed features

    Example:
        >>> gc_15m, dxy_15m = extract_htf_candles_by_timeframe(multi_tf_data, "15m")
        >>> gc_1h, dxy_1h = extract_htf_candles_by_timeframe(multi_tf_data, "1h")
        >>> features_15m, features_1h = compute_htf_features_vectorized(
        ...     gc_15m, dxy_15m, gc_1h, dxy_1h
        ... )
    """
    # Scale down dxy_window for HTF to ensure faster warmup (match streaming approach)
    dxy_window_1h = max(20, dxy_window // 2)
    dxy_window_15m = max(25, int(dxy_window // 1.5))
    # Convert candles to DataFrames
    gc_15m_df = candles_to_dataframe(gc_candles_15m, "15m") if gc_candles_15m else None
    dxy_15m_df = (
        candles_to_dataframe(dxy_candles_15m, "15m") if dxy_candles_15m else None
    )
    gc_1h_df = candles_to_dataframe(gc_candles_1h, "1h") if gc_candles_1h else None
    dxy_1h_df = candles_to_dataframe(dxy_candles_1h, "1h") if dxy_candles_1h else None

    # Compute 15m features
    features_15m_df = None
    if gc_15m_df is not None and dxy_15m_df is not None and len(gc_15m_df) > 0:
        # Prepare for aggregation (add ts_event column)
        gc_15m_work = gc_15m_df.copy()
        gc_15m_work["ts_event"] = gc_15m_work.index
        gc_15m_work = gc_15m_work.reset_index(drop=True)

        dxy_15m_work = dxy_15m_df.copy()
        dxy_15m_work["ts_event"] = dxy_15m_work.index
        dxy_15m_work = dxy_15m_work.reset_index(drop=True)

        # Compute features (use scaled-down dxy_window for 15m)
        features_15m_df = aggregate_features(
            gc_15m_work,
            dxy_15m_work,
            "15m",
            indicators={
                "vwap": {"session_reset": True},
                "rsi": {"period": rsi_period},
                "ema": {"periods": ema_periods or [9, 20, 50]},
                "dxy_correlation": {"window": dxy_window_15m},
            },
        )

        # Add structure labels
        structure_labels_15m = calculate_structure_labels(
            features_15m_df, swing_window=swing_window
        )
        features_15m_df["structure_label"] = structure_labels_15m
        features_15m_df["structure_type"] = structure_labels_15m

        # Add VWAP deviation
        if "vwap" in features_15m_df.columns:
            vwap_deviation_15m = calculate_vwap_deviation(features_15m_df)
            features_15m_df["vwap_deviation"] = vwap_deviation_15m

        # Set timestamp index
        if "ts_event" in features_15m_df.columns:
            features_15m_df = features_15m_df.set_index("ts_event")

        logger.debug(f"Computed 15m features: {len(features_15m_df)} rows")

    # Compute 1h features
    features_1h_df = None
    if gc_1h_df is not None and dxy_1h_df is not None and len(gc_1h_df) > 0:
        # Prepare for aggregation (add ts_event column)
        gc_1h_work = gc_1h_df.copy()
        gc_1h_work["ts_event"] = gc_1h_work.index
        gc_1h_work = gc_1h_work.reset_index(drop=True)

        dxy_1h_work = dxy_1h_df.copy()
        dxy_1h_work["ts_event"] = dxy_1h_work.index
        dxy_1h_work = dxy_1h_work.reset_index(drop=True)

        # Compute features (use scaled-down dxy_window for 1h)
        features_1h_df = aggregate_features(
            gc_1h_work,
            dxy_1h_work,
            "1h",
            indicators={
                "vwap": {"session_reset": True},
                "rsi": {"period": rsi_period},
                "ema": {"periods": ema_periods or [9, 20, 50]},
                "dxy_correlation": {"window": dxy_window_1h},
            },
        )

        # Add structure labels
        structure_labels_1h = calculate_structure_labels(
            features_1h_df, swing_window=swing_window
        )
        features_1h_df["structure_label"] = structure_labels_1h
        features_1h_df["structure_type"] = structure_labels_1h
        
        # Log structure label distribution
        valid_labels = structure_labels_1h.dropna()
        logger.info(
            f"1H structure labels: {len(valid_labels)} valid out of {len(structure_labels_1h)}, "
            f"distribution: {valid_labels.value_counts().to_dict() if len(valid_labels) > 0 else 'none'}"
        )

        # Add VWAP deviation
        if "vwap" in features_1h_df.columns:
            vwap_deviation_1h = calculate_vwap_deviation(features_1h_df)
            features_1h_df["vwap_deviation"] = vwap_deviation_1h

        # Set timestamp index
        if "ts_event" in features_1h_df.columns:
            features_1h_df = features_1h_df.set_index("ts_event")

        logger.debug(f"Computed 1h features: {len(features_1h_df)} rows")

    return features_15m_df, features_1h_df


def _precompute_htf_features(
    multi_tf_data: MultiTimeframeData,
    rsi_period: int = 14,
    ema_periods: list[int] | None = None,
    dxy_window: int = 50,
    swing_window: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pre-compute all HTF features from MultiTimeframeData.

    Helper function that extracts HTF candles and computes features vectorized.

    Args:
        multi_tf_data: MultiTimeframeData with synchronized bars
        rsi_period: RSI calculation period
        ema_periods: List of EMA periods
        dxy_window: DXY correlation window
        swing_window: Structure label swing window

    Returns:
        Tuple of (features_15m_df, features_1h_df)
    """
    # Extract HTF candles
    gc_15m, dxy_15m = extract_htf_candles_by_timeframe(multi_tf_data, "15m")
    gc_1h, dxy_1h = extract_htf_candles_by_timeframe(multi_tf_data, "1h")

    # Compute features
    return compute_htf_features_vectorized(
        gc_15m,
        dxy_15m,
        gc_1h,
        dxy_1h,
        rsi_period=rsi_period,
        ema_periods=ema_periods,
        dxy_window=dxy_window,
        swing_window=swing_window,
    )

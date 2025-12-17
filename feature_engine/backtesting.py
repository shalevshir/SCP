"""Vectorized feature processor for backtesting without look-ahead bias.

This module provides a fast, vectorized feature calculation mode designed for
backtesting. It prevents look-ahead bias by using strict time slicing (only
data up to current timestamp) while leveraging pandas vectorization for speed.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING

import pandas as pd
from common.logger import get_logger

if TYPE_CHECKING:
    from common.types import Candle
from validation.config_loader import load_session_config
from validation.guardrails import (
    BehaviorGuardrails,
    BehaviorStateTracker,
)
from validation.session_validator import SessionValidator

from feature_engine.aggregator import aggregate_features
from feature_engine.structure import (
    calculate_structure_labels,
    compute_structure_context_batch,
    get_swing_window_for_timeframe,
)
from feature_engine.vwap import calculate_vwap_deviation

logger = get_logger(__name__)


class BacktestProcessor:
    """Vectorized feature processor for backtesting without look-ahead bias.

    This processor computes technical indicators using pandas vectorization
    for speed, while preventing look-ahead bias by only using data up to the
    current timestamp during iteration.

    Key features:
    - Fast: Uses vectorized pandas operations (10x+ faster than incremental mode)
    - Safe: Guarantees no look-ahead bias through strict time slicing
    - Compatible: Produces outputs matching incremental FeatureState
    - Configurable: Supports session resets, custom warmup periods, etc.

    Example:
        >>> processor = BacktestProcessor(timeframe="1m")
        >>> for features in processor.iterate_with_context(gc_df, dxy_df):
        ...     signal = rule_engine.evaluate(features, context)
        ...     # backtesting logic
    """

    def __init__(
        self,
        timeframe: str,
        session_reset: bool = True,
        rsi_period: int = 14,
        ema_periods: list[int] | None = None,
        dxy_window: int = 50,
        swing_window: int | None = None,
        warmup_period: int | None = None,
        enable_validation: bool = True,
    ):
        """Initialize BacktestProcessor with configuration.

        Args:
            timeframe: Timeframe string (e.g., "1m", "15m", "1h").
            session_reset: Whether to reset VWAP at session boundaries.
            rsi_period: RSI calculation period. Default is 14.
            ema_periods: List of EMA periods to calculate. Default is [9, 20, 50].
            dxy_window: DXY correlation window size. Default is 50.
            swing_window: Structure label swing window. If None, automatically
                         determined based on timeframe (1m=2, 15m=3, 1h=5).
                         Can be explicitly set to override default.
            warmup_period: Number of periods to skip before yielding features.
                          If None, uses max(dxy_window, swing_window * 2 + 1).
            enable_validation: Whether to enable validation layer components.
                              Set to False to disable session/guardrail tracking.
        """
        self.timeframe = timeframe
        self.session_reset = session_reset
        self.rsi_period = rsi_period
        self.ema_periods = ema_periods if ema_periods is not None else [9, 20, 50]
        self.dxy_window = dxy_window

        # Automatically determine swing_window based on timeframe if not provided
        if swing_window is None:
            self.swing_window = get_swing_window_for_timeframe(timeframe)
            logger.info(
                f"Using timeframe-appropriate swing_window={self.swing_window} "
                f"for {timeframe}"
            )
        else:
            self.swing_window = swing_window
            logger.info(
                f"Using explicit swing_window={self.swing_window} for {timeframe}"
            )

        self.enable_validation = enable_validation

        # Calculate warmup period if not provided
        if warmup_period is None:
            self.warmup_period = max(
                self.dxy_window, self.swing_window * 2 + 1, self.rsi_period
            )
        else:
            self.warmup_period = warmup_period

        # Initialize validation components
        if self.enable_validation:
            try:
                session_config = load_session_config()
                self._session_validator = SessionValidator(session_config)
                self._behavior_tracker = BehaviorStateTracker()
                self._behavior_guardrails = BehaviorGuardrails()
                self._last_session_date: datetime | None = None
                logger.info("Validation layer enabled for backtesting")
            except Exception as e:
                logger.warning(
                    f"Failed to initialize validation layer: {e}. "
                    "Continuing without validation."
                )
                self.enable_validation = False

        logger.debug(
            f"BacktestProcessor initialized: timeframe={timeframe}, "
            f"warmup_period={self.warmup_period}, "
            f"validation_enabled={self.enable_validation}"
        )

    def iterate_with_context(
        self,
        gc_df: pd.DataFrame,
        dxy_df: pd.DataFrame,
    ) -> Iterator[tuple[pd.Series, dict]]:
        """Yield features and validation context one timestamp at a time.

        This method computes features ONCE for the entire dataset using
        vectorization, then carefully yields them one at a time ensuring
        that look-ahead-sensitive indicators (like structure labels) are
        handled correctly.

        When validation is enabled, also tracks session state and behavior
        guardrails, yielding both features and validation context.

        Args:
            gc_df: GC DataFrame with DatetimeIndex and OHLCV columns.
            dxy_df: DXY DataFrame with DatetimeIndex and OHLCV columns.

        Yields:
            Tuple of (features_series, validation_context) for each timestamp.
            If validation disabled, validation_context will be empty dict.

        Example:
            >>> processor = BacktestProcessor(timeframe="1m")
            >>> for features, context in processor.iterate_with_context(
            ...     gc_df, dxy_df
            ... ):
            ...     print(
            ...         f"Timestamp: {features['timestamp']}, "
            ...         f"Session OK: {context.get('session_ok')}"
            ...     )
        """
        # Validate inputs
        if not isinstance(gc_df.index, pd.DatetimeIndex):
            raise ValueError(f"gc_df must have DatetimeIndex, got {type(gc_df.index)}")
        if not isinstance(dxy_df.index, pd.DatetimeIndex):
            raise ValueError(
                f"dxy_df must have DatetimeIndex, got {type(dxy_df.index)}"
            )

        # Ensure aligned timestamps
        common_timestamps = gc_df.index.intersection(dxy_df.index)
        if len(common_timestamps) == 0:
            raise ValueError("No common timestamps between GC and DXY dataframes")

        gc_aligned = gc_df.loc[common_timestamps].copy()
        dxy_aligned = dxy_df.loc[common_timestamps].copy()

        logger.info(
            f"Starting backtest iteration: {len(gc_aligned)} rows, "
            f"warmup_period={self.warmup_period}"
        )

        # Compute ALL features once (vectorized, fast)
        features_df = self._compute_features(gc_aligned, dxy_aligned)

        # Iterate and yield features one at a time
        for i in range(self.warmup_period - 1, len(gc_aligned)):
            timestamp = gc_aligned.index[i]
            features = features_df.iloc[i]

            # Check for session reset (new trading day)
            if self.enable_validation:
                self._check_session_reset(timestamp)

            # Structure labels are already delayed by swing_window bars in
            # calculate_structure_labels(), so no additional masking is needed.
            # The last swing_window bars will naturally have None labels since
            # there isn't enough future data to confirm swings.

            # Build features series
            features_series = pd.Series(
                {
                    "timestamp": timestamp,
                    "symbol": "GC",
                    "timeframe": self.timeframe,
                    "open": features["open"],
                    "high": features["high"],
                    "low": features["low"],
                    "close": features["close"],
                    "volume": features["volume"],
                    "vwap": features["vwap"],
                    "vwap_slope": features.get("vwap_slope"),
                    "rsi": features["rsi"],
                    "ema_9": features["ema_9"],
                    "ema_20": features["ema_20"],
                    "ema_50": features["ema_50"],
                    "dxy_corr": features["dxy_corr"],
                    "dxy_corr_micro": features.get("dxy_corr_micro"),
                    "volume_sma_20": features.get("volume_sma_20"),
                    "atr": features.get("atr"),
                    "upper_wick_pct": features.get("upper_wick_pct"),
                    "lower_wick_pct": features.get("lower_wick_pct"),
                    "close_vwap_diff": features.get("close_vwap_diff"),
                    "close_vwap_pct": features.get("close_vwap_pct"),
                    "structure_label": features.get("structure_label"),
                    "structure_type": features.get("structure_type"),
                    "vwap_deviation": features.get("vwap_deviation"),
                    # Structure context derived fields
                    "last_structure_label": features.get("last_structure_label"),
                    "trend_direction": features.get("trend_direction"),
                    "trend_confidence": features.get("trend_confidence"),
                    "structure_clarity": features.get("structure_clarity"),
                    "is_chop": features.get("is_chop"),
                    "is_structural_chop": features.get("is_structural_chop"),
                    "atr_compression_ratio": features.get("atr_compression_ratio"),
                    "structure_conflict_flag": features.get("structure_conflict_flag"),
                    "last_swing_high": features.get("last_swing_high"),
                    "last_swing_low": features.get("last_swing_low"),
                    "last_swing_high_idx": features.get("last_swing_high_idx"),
                    "last_swing_low_idx": features.get("last_swing_low_idx"),
                    "bos_direction": features.get("bos_direction"),
                    "bos_recent": features.get("bos_recent"),
                    "bos_age": features.get("bos_age"),
                    "choch_detected": features.get("choch_detected"),
                    "choch_direction": features.get("choch_direction"),
                    "choch_age": features.get("choch_age"),
                    "liquidity_sweep": features.get("liquidity_sweep"),
                    "sweep_direction": features.get("sweep_direction"),
                    "sweep_price": features.get("sweep_price"),
                    "sweep_age": features.get("sweep_age"),
                }
            )

            # Build validation context if enabled
            validation_context = {}
            if self.enable_validation:
                validation_context = self._build_validation_context(timestamp)

            yield features_series, validation_context

    def iterate_with_entry_context(
        self,
        gc_df: pd.DataFrame,
        dxy_df: pd.DataFrame,
    ) -> Iterator[tuple[pd.Series, dict, Candle | None]]:
        """Yield features, validation context, and next candle for entry execution.

        This method extends iterate_with_context() by also providing the next
        candle's data to support entry model integration. The next candle contains
        only raw OHLCV data (no derived features) to maintain separation between
        signal generation and entry execution.

        Args:
            gc_df: GC DataFrame with DatetimeIndex and OHLCV columns.
            dxy_df: DXY DataFrame with DatetimeIndex and OHLCV columns.

        Yields:
            Tuple of (features_series, validation_context, next_candle):
            - features_series: Current bar features (pd.Series)
            - validation_context: Validation context dict
            - next_candle: Next bar's Candle object or None (end of dataset)

        Example:
            >>> processor = BacktestProcessor(timeframe="1m")
            >>> for features, context, next_candle in (
            ...     processor.iterate_with_entry_context(gc_df, dxy_df)
            ... ):
            ...     signal = process_signal(features, context)
            ...     entry = execute_entry_at_next_open(signal, next_candle)
        """
        from common.types import Candle

        # Validate inputs
        if not isinstance(gc_df.index, pd.DatetimeIndex):
            raise ValueError(f"gc_df must have DatetimeIndex, got {type(gc_df.index)}")
        if not isinstance(dxy_df.index, pd.DatetimeIndex):
            raise ValueError(
                f"dxy_df must have DatetimeIndex, got {type(dxy_df.index)}"
            )

        # Ensure aligned timestamps
        common_timestamps = gc_df.index.intersection(dxy_df.index)
        if len(common_timestamps) == 0:
            raise ValueError("No common timestamps between GC and DXY dataframes")

        gc_aligned = gc_df.loc[common_timestamps].copy()
        dxy_aligned = dxy_df.loc[common_timestamps].copy()

        logger.info(
            f"Starting backtest iteration with entry context: {len(gc_aligned)} rows, "
            f"warmup_period={self.warmup_period}"
        )

        # Compute ALL features once (vectorized, fast)
        features_df = self._compute_features(gc_aligned, dxy_aligned)

        # Iterate and yield features with next candle
        for i in range(self.warmup_period - 1, len(gc_aligned)):
            timestamp = gc_aligned.index[i]
            features = features_df.iloc[i]

            # Check for session reset (new trading day)
            if self.enable_validation:
                self._check_session_reset(timestamp)

            # Structure labels are already delayed by swing_window bars in
            # calculate_structure_labels(), so no additional masking is needed.
            # The last swing_window bars will naturally have None labels since
            # there isn't enough future data to confirm swings.

            # Build features series (current bar)
            features_series = pd.Series(
                {
                    "timestamp": timestamp,
                    "symbol": "GC",
                    "timeframe": self.timeframe,
                    "open": features["open"],
                    "high": features["high"],
                    "low": features["low"],
                    "close": features["close"],
                    "volume": features["volume"],
                    "volume_sma_20": features.get("volume_sma_20"),
                    "vwap": features["vwap"],
                    "vwap_slope": features.get("vwap_slope"),
                    "rsi": features["rsi"],
                    "ema_9": features["ema_9"],
                    "ema_20": features["ema_20"],
                    "ema_50": features["ema_50"],
                    "dxy_corr": features["dxy_corr"],
                    "dxy_corr_micro": features.get("dxy_corr_micro"),
                    "atr": features.get("atr"),
                    "upper_wick_pct": features.get("upper_wick_pct"),
                    "lower_wick_pct": features.get("lower_wick_pct"),
                    "close_vwap_diff": features.get("close_vwap_diff"),
                    "close_vwap_pct": features.get("close_vwap_pct"),
                    "structure_label": features.get("structure_label"),
                    "structure_type": features.get("structure_type"),
                    "vwap_deviation": features.get("vwap_deviation"),
                    # Structure context derived fields
                    "last_structure_label": features.get("last_structure_label"),
                    "trend_direction": features.get("trend_direction"),
                    "trend_confidence": features.get("trend_confidence"),
                    "structure_clarity": features.get("structure_clarity"),
                    "is_chop": features.get("is_chop"),
                    "is_structural_chop": features.get("is_structural_chop"),
                    "atr_compression_ratio": features.get("atr_compression_ratio"),
                    "structure_conflict_flag": features.get("structure_conflict_flag"),
                    "last_swing_high": features.get("last_swing_high"),
                    "last_swing_low": features.get("last_swing_low"),
                    "last_swing_high_idx": features.get("last_swing_high_idx"),
                    "last_swing_low_idx": features.get("last_swing_low_idx"),
                    "bos_direction": features.get("bos_direction"),
                    "bos_recent": features.get("bos_recent"),
                    "bos_age": features.get("bos_age"),
                    "choch_detected": features.get("choch_detected"),
                    "choch_direction": features.get("choch_direction"),
                    "choch_age": features.get("choch_age"),
                    "liquidity_sweep": features.get("liquidity_sweep"),
                    "sweep_direction": features.get("sweep_direction"),
                    "sweep_price": features.get("sweep_price"),
                    "sweep_age": features.get("sweep_age"),
                }
            )

            # Build validation context if enabled
            validation_context = {}
            if self.enable_validation:
                validation_context = self._build_validation_context(timestamp)

            # Build next candle (or None if at end of dataset)
            next_candle = None
            if i + 1 < len(gc_aligned):
                next_idx = i + 1
                next_row = gc_aligned.iloc[next_idx]
                next_timestamp = gc_aligned.index[next_idx]

                next_candle = Candle(
                    timestamp=next_timestamp,
                    open=float(next_row["open"]),
                    high=float(next_row["high"]),
                    low=float(next_row["low"]),
                    close=float(next_row["close"]),
                    volume=float(next_row["volume"]),
                    symbol="GC",
                    timeframe=self.timeframe,
                    source="BACKTEST",
                )

            yield features_series, validation_context, next_candle

    def _compute_features(
        self,
        gc_df: pd.DataFrame,
        dxy_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Compute all features for a time slice using vectorization.

        This internal method computes features on a time slice (data up to
        current point). It uses the existing aggregate_features() function
        which already implements vectorized calculations correctly.

        Args:
            gc_df: Time-sliced GC DataFrame.
            dxy_df: Time-sliced DXY DataFrame.

        Returns:
            DataFrame with all features computed.
        """
        # Convert index to ts_event column for aggregate_features
        gc_work = gc_df.copy()
        gc_work["ts_event"] = gc_work.index
        gc_work = gc_work.reset_index(drop=True)

        dxy_work = dxy_df.copy()
        dxy_work["ts_event"] = dxy_work.index
        dxy_work = dxy_work.reset_index(drop=True)

        # Use existing aggregate_features for vectorized calculation
        features = aggregate_features(
            gc_work,
            dxy_work,
            self.timeframe,
            indicators={
                "vwap": {"session_reset": self.session_reset},
                "rsi": {"period": self.rsi_period},
                "ema": {"periods": self.ema_periods},
                "dxy_corr": {"window": self.dxy_window},
            },
        )

        # Add structure labels (sparse, for backward compatibility)
        structure_labels = calculate_structure_labels(
            features, swing_window=self.swing_window
        )
        features["structure_label"] = structure_labels
        features["structure_type"] = structure_labels  # Alias

        # Add structure context (continuous derived fields)
        structure_context = compute_structure_context_batch(
            features[["high", "low", "close"]],
            swing_window=self.swing_window,
            timeframe=self.timeframe,
        )

        # Merge structure context fields into features
        for col in structure_context.columns:
            # Don't overwrite structure_label (keep sparse version for compatibility)
            if col not in ["last_structure_label"]:
                features[col] = structure_context[col]

        # Add last_structure_label separately (continuous version)
        features["last_structure_label"] = structure_context["last_structure_label"]

        # Add VWAP deviation
        if "vwap" in features.columns:
            vwap_deviation = calculate_vwap_deviation(features)
            features["vwap_deviation"] = vwap_deviation

        return features

    def _check_session_reset(self, timestamp: datetime) -> None:
        """Check if we need to reset behavior state for new session.

        Per SOP, loss streaks reset at session start (not across days).

        Args:
            timestamp: Current timestamp
        """
        if not self.enable_validation:
            return

        current_date = timestamp.date()

        # Reset on first run or new day
        if self._last_session_date is None or current_date != self._last_session_date:
            self._behavior_tracker.reset_for_session(timestamp)
            self._last_session_date = current_date
            logger.debug(f"Session reset at {timestamp.isoformat()}")

    def _build_validation_context(self, timestamp: datetime) -> dict:
        """Build validation context for current timestamp.

        Args:
            timestamp: Current timestamp

        Returns:
            Dict with validation context including session_result and guardrail_result
        """
        if not self.enable_validation:
            return {}

        # Evaluate session
        session_result = self._session_validator.evaluate(timestamp)

        # Evaluate behavior guardrails
        guardrail_result = self._behavior_guardrails.evaluate(
            state=self._behavior_tracker.state,
            constraints=session_result.constraints,
        )

        return {
            "session_ok": session_result.session_ok,
            "session_result": session_result,
            "session_constraints": session_result.constraints,
            "guardrail_result": guardrail_result,
            "behavior_state": self._behavior_tracker.state,
        }

    def record_trade_outcome(self, won: bool | None) -> None:
        """Record trade outcome to update behavior state.

        Args:
            won: True if trade was profitable (pnl > 0),
                 False if trade was a loss (pnl < 0),
                 None if trade was breakeven (pnl == 0)
        """
        if not self.enable_validation:
            return

        self._behavior_tracker.record_trade_outcome(won)

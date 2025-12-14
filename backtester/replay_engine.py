"""Historical replay engine for SOP validators.

This module provides a replay engine that runs all SOP validators incrementally
over historical data, ensuring validation results match live behavior. The engine
tracks evolving state (loss streaks, daily risk) that resets per session and
ensures no lookahead bias.

Key Features:
- Incremental validation (candle-by-candle)
- State evolution tracking (loss streaks, daily risk)
- Session-based resets
- No lookahead bias
- Integration with existing validation components
"""

from collections.abc import Iterator
from datetime import datetime

import pandas as pd
from common.logger import get_logger
from feature_engine.backtesting import BacktestProcessor
from validation.guardrails import BehaviorStateTracker

logger = get_logger(__name__)


class ReplayEngine:
    """Historical replay engine for SOP validators.

    This engine orchestrates the full validation pipeline over historical data,
    ensuring all validators run incrementally with proper state management.
    It wraps BacktestProcessor and adds state tracking for loss streaks and
    daily risk limits.

    The engine ensures:
    - Validators run incrementally (no lookahead)
    - State evolves correctly (loss streaks, daily risk)
    - Session resets work properly
    - Validation flags are produced per candle
    - Trade outcomes update behavior state

    Example:
        >>> engine = ReplayEngine(timeframe="1m")
        >>> for features, validation_context in engine.replay(gc_df, dxy_df):
        ...     # Process signal with validation
        ...     signal = process_signal(features, validation_context)
        ...     if signal.confidence == "A+":
        ...         # Execute trade
        ...         ...
        ...         # Record outcome
        ...         engine.record_trade_outcome(won=True)
    """

    def __init__(
        self,
        timeframe: str,
        enable_validation: bool = True,
    ):
        """Initialize replay engine.

        Args:
            timeframe: Timeframe string (e.g., "1m", "15m", "1h")
            enable_validation: Whether to enable validation layer (default: True)
        """
        self.timeframe = timeframe
        self.enable_validation = enable_validation

        # Initialize processor with validation enabled
        self._processor = BacktestProcessor(
            timeframe=timeframe,
            enable_validation=enable_validation,
        )

        logger.info(
            f"ReplayEngine initialized: timeframe={timeframe}, "
            f"validation_enabled={enable_validation}"
        )

    def replay(
        self,
        gc_df: pd.DataFrame,
        dxy_df: pd.DataFrame,
    ) -> Iterator[tuple[pd.Series, dict]]:
        """Replay historical data with incremental validation.

        This method iterates through historical data candle-by-candle, running
        all SOP validators incrementally. It ensures no lookahead bias by only
        using data up to the current timestamp.

        The validation context includes:
        - Session validation (time windows, seasonality)
        - Behavior guardrails (loss streaks, fatigue flags)
        - All validation flags per candle

        Args:
            gc_df: GC DataFrame with DatetimeIndex and OHLCV columns
            dxy_df: DXY DataFrame with DatetimeIndex and OHLCV columns

        Yields:
            Tuple of (features_series, validation_context) for each candle.
            validation_context contains:
                - session_ok: Whether session is active
                - session_result: SessionResult from SessionValidator
                - session_constraints: SessionConstraints for current season
                - guardrail_result: GuardrailResult from BehaviorGuardrails
                - behavior_state: Current BehaviorState snapshot

        Example:
            >>> engine = ReplayEngine(timeframe="1m")
            >>> for features, context in engine.replay(gc_df, dxy_df):
            ...     print(f"Timestamp: {features['timestamp']}")
            ...     print(f"Session OK: {context.get('session_ok')}")
            ...     print(f"Loss streak: {context.get('behavior_state').consecutive_losses}")
        """
        logger.info(
            f"Starting replay: {len(gc_df)} candles, " f"timeframe={self.timeframe}"
        )

        # Use BacktestProcessor's iterate_with_context which already handles:
        # - Incremental feature computation (no lookahead)
        # - Session resets
        # - Validation context building
        yield from self._processor.iterate_with_context(gc_df, dxy_df)

        logger.info("Replay complete")

    def record_trade_outcome(self, won: bool | None) -> None:
        """Record trade outcome to update behavior state.

        This method updates the behavior state tracker with trade outcomes,
        which affects loss streak tracking and guardrail evaluation.

        Args:
            won: True if trade was profitable (pnl > 0),
                 False if trade was a loss (pnl < 0),
                 None if trade was breakeven (pnl == 0)

        Example:
            >>> engine = ReplayEngine(timeframe="1m")
            >>> # ... process trade ...
            >>> engine.record_trade_outcome(won=True)  # Win
            >>> engine.record_trade_outcome(won=False)  # Loss
            >>> engine.record_trade_outcome(won=None)  # Breakeven
        """
        if not self.enable_validation:
            logger.debug("Validation disabled - skipping trade outcome recording")
            return

        self._processor.record_trade_outcome(won)
        logger.debug(f"Trade outcome recorded: won={won}")

    @property
    def behavior_state(self) -> BehaviorStateTracker | None:
        """Get current behavior state tracker.

        Returns:
            BehaviorStateTracker if validation enabled, None otherwise
        """
        if not self.enable_validation:
            return None

        # Access the internal tracker from BacktestProcessor
        # Note: This is a bit of a hack, but BacktestProcessor doesn't expose
        # the tracker directly. We could enhance BacktestProcessor to expose it.
        if hasattr(self._processor, "_behavior_tracker"):
            return self._processor._behavior_tracker
        return None

    def get_validation_context_at_timestamp(
        self,
        gc_df: pd.DataFrame,
        dxy_df: pd.DataFrame,
        timestamp: datetime,
    ) -> dict | None:
        """Get validation context for a specific timestamp.

        This is useful for testing or debugging - it allows you to get the
        validation context that would be produced at a specific timestamp
        without replaying the entire dataset.

        Args:
            gc_df: GC DataFrame with DatetimeIndex
            dxy_df: DXY DataFrame with DatetimeIndex
            timestamp: Target timestamp

        Returns:
            Validation context dict or None if timestamp not found

        Example:
            >>> engine = ReplayEngine(timeframe="1m")
            >>> context = engine.get_validation_context_at_timestamp(
            ...     gc_df, dxy_df, datetime(2024, 1, 15, 10, 30)
            ... )
        """
        # Find the index of the timestamp
        try:
            idx = gc_df.index.get_loc(timestamp)
        except KeyError:
            logger.warning(f"Timestamp {timestamp} not found in dataset")
            return None

        # Replay up to that timestamp
        # We need to create a slice up to and including the timestamp
        gc_slice = gc_df.iloc[: idx + 1]
        dxy_slice = dxy_df.iloc[: idx + 1]

        # Find the matching context by replaying
        for features, context in self.replay(gc_slice, dxy_slice):
            if features["timestamp"] == timestamp:
                return context

        return None

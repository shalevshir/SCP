"""Streaming HTF Bias Calculator for incremental processing.

This module provides StreamingHTFBiasCalculator that maintains separate
streaming processors for 1H and 15M timeframes and calls the existing
compute_htf_bias() function to generate HTFBias objects.

Architecture: Detects bar boundaries and delegates to existing HTF calculator.
"""

from datetime import datetime

import pandas as pd
from scp_shared.common.logger import get_logger
from scp_shared.common.types import Candle
from scp_shared.indicators.streaming import StreamingFeatureProcessor

from scp_shared.rule_engine.htf.calculator import compute_htf_bias
from scp_shared.rule_engine.htf.types import HTFBias

logger = get_logger(__name__)


class StreamingHTFBiasCalculator:
    """Streaming HTF bias calculator with multi-timeframe support.

    Maintains separate streaming processors for 1H and 15M timeframes,
    detects bar boundaries, and calls existing compute_htf_bias() function.

    Attributes:
        processor_1h: Streaming feature processor for 1H timeframe
        processor_15m: Streaming feature processor for 15M timeframe
        current_1h_bar: Current 1H bar being built from 1M bars
        current_15m_bar: Current 15M bar being built from 1M bars
        current_htf_bias: Most recent HTF bias calculation
        features_1h: Most recent 1H features
        features_15m: Most recent 15M features
    """

    def __init__(self):
        """Initialize streaming HTF bias calculator."""
        # Create streaming processors for each timeframe
        # Use smaller swing_window (3 instead of 5) to need fewer bars for structure detection
        # swing_window=3 needs 7 bars, swing_window=5 needs 11 bars
        # 1H with swing_window=3 needs 7 hours instead of 11 hours
        # 15M with swing_window=3 needs 7*15min = 1.75 hours instead of 2.75 hours
        self.processor_1h = StreamingFeatureProcessor(timeframe="1h", swing_window=3)
        self.processor_15m = StreamingFeatureProcessor(timeframe="15m", swing_window=3)
        # Add 1M processor for micro correlation (needed for DXY alignment)
        self.processor_1m = StreamingFeatureProcessor(timeframe="1m", swing_window=2)

        # Track current HTF bars being built
        self.current_1h_timestamp: datetime | None = None
        self.current_15m_timestamp: datetime | None = None

        # Store current state
        self.current_htf_bias: HTFBias | None = None
        self.features_1h: pd.Series = pd.Series(dtype=object)
        self.features_15m: pd.Series = pd.Series(dtype=object)
        self.features_1m: pd.Series = pd.Series(dtype=object)

        # Historical buffers for HTF calculation (needed for structure/FVG detection)
        self.df_1h_buffer: list[dict] = []
        self.df_15m_buffer: list[dict] = []
        self.dxy_1h_buffer: list[dict] = []

        # HTF candle aggregation state (properly aggregates 1M -> HTF OHLCV)
        # 15M GC aggregation
        self._gc_15m_start: datetime | None = None
        self._gc_15m_open: float | None = None
        self._gc_15m_high: float | None = None
        self._gc_15m_low: float | None = None
        self._gc_15m_close: float | None = None
        self._gc_15m_volume: float = 0.0

        # 1H GC aggregation
        self._gc_1h_start: datetime | None = None
        self._gc_1h_open: float | None = None
        self._gc_1h_high: float | None = None
        self._gc_1h_low: float | None = None
        self._gc_1h_close: float | None = None
        self._gc_1h_volume: float = 0.0

        # 1H DXY aggregation
        self._dxy_1h_start: datetime | None = None
        self._dxy_1h_open: float | None = None
        self._dxy_1h_high: float | None = None
        self._dxy_1h_low: float | None = None
        self._dxy_1h_close: float | None = None

        # Track current 1H period for DXY buffer updates
        # This mimics the backtest's behavior where the buffer entry is updated in-place
        # as the bar develops, rather than keeping stale data
        self._current_dxy_1h_in_buffer: bool = False

        # Cache for DXY chop detection result
        # The backtest caches chop value and only updates at specific boundaries:
        # - At 1H close: recalculate with nearly-complete partial bar
        # - At new hour (non-first): recalculate with new partial bar to check if chop clears
        # - At other times: use cached value
        self._cached_dxy_chop: bool = False
        self._first_hour_of_session: int = 7  # First trading hour (adjust as needed)

        # Swept levels tracking for untouched liquidity computation
        # Tracks price levels that have been swept (violated) so they can be excluded
        # from untouched liquidity targets
        self.swept_levels_high: set[float] = set()  # Swing highs that have been swept
        self.swept_levels_low: set[float] = set()  # Swing lows that have been swept

        logger.info("Streaming HTF bias calculator initialized")

    def update(self, gc_bar: Candle, dxy_bar: Candle) -> HTFBias | None:
        """Update with new 1M bar and compute HTF bias if boundaries reached.

        Args:
            gc_bar: New 1M Gold candle
            dxy_bar: New 1M DXY candle

        Returns:
            HTFBias object if boundary reached, else None
        """
        # Update 1M features (for micro correlation in DXY alignment)
        self.features_1m = self.processor_1m.update(gc_bar, dxy_bar)

        # Update HTF candle aggregation (must happen before boundary check)
        self._update_15m_aggregation(gc_bar)
        self._update_1h_aggregation(gc_bar, dxy_bar)

        # Detect 15M boundary
        is_15m_close = self._is_15m_boundary(gc_bar.timestamp)

        # Detect 1H boundary
        is_1h_close = self._is_1h_boundary(gc_bar.timestamp)

        # Also trigger HTF recalculation at start of new 1H period (matches backtest behavior)
        # Backtest recalculates HTF bias every bar; we optimize by recalculating at 15M + hourly
        current_hour = gc_bar.timestamp.hour
        is_new_hour = (
            self.current_1h_timestamp is None
            or self.current_1h_timestamp.hour != current_hour
        )

        # At 15M boundary, emit aggregated candle and update processor
        if is_15m_close:
            # Create aggregated 15M candle from accumulated values
            if self._gc_15m_start is not None:
                gc_15m_candle = Candle(
                    timestamp=self._gc_15m_start,
                    symbol="GC",
                    timeframe="15m",
                    source="aggregated",
                    open=self._gc_15m_open or gc_bar.open,
                    high=self._gc_15m_high or gc_bar.high,
                    low=self._gc_15m_low or gc_bar.low,
                    close=self._gc_15m_close or gc_bar.close,
                    volume=self._gc_15m_volume,
                )
                # Pass aggregated 15M candle to processor (not 1M candle)
                self.features_15m = self.processor_15m.update(gc_15m_candle, dxy_bar)
            else:
                # Fallback if no aggregation happened (shouldn't occur)
                self.features_15m = self.processor_15m.update(gc_bar, dxy_bar)
            # Store properly aggregated 15M bar in historical buffer
            self._emit_15m_to_buffer()
            logger.debug(f"15M bar closed at {gc_bar.timestamp}")

        # At 1H boundary, emit aggregated candle and update processor
        if is_1h_close:
            # Create aggregated 1H candle from accumulated values
            if self._gc_1h_start is not None:
                gc_1h_candle = Candle(
                    timestamp=self._gc_1h_start,
                    symbol="GC",
                    timeframe="1h",
                    source="aggregated",
                    open=self._gc_1h_open or gc_bar.open,
                    high=self._gc_1h_high or gc_bar.high,
                    low=self._gc_1h_low or gc_bar.low,
                    close=self._gc_1h_close or gc_bar.close,
                    volume=self._gc_1h_volume,
                )
                # Pass aggregated 1H candle to processor (not 1M candle)
                self.features_1h = self.processor_1h.update(gc_1h_candle, dxy_bar)
            else:
                # Fallback if no aggregation happened (shouldn't occur)
                self.features_1h = self.processor_1h.update(gc_bar, dxy_bar)
            # Store properly aggregated 1H bar in historical buffer
            self._emit_1h_to_buffer()
            logger.info(
                f"1H bar closed at {gc_bar.timestamp} | "
                f"1H bars in buffer: {len(self.df_1h_buffer)} | "
                f"1H structure: {self.features_1h.get('structure_label', 'N/A')}"
            )

        # Compute HTF bias when we have both 1H and 15M features
        # Trigger on 15M close, 1H close, OR start of new hour (matches backtest every-bar behavior)
        if (
            (is_1h_close or is_15m_close or is_new_hour)
            and not self.features_1h.empty
            and not self.features_15m.empty
        ):
            try:
                # Convert buffers to DataFrames for structure detection
                # IMPORTANT: Include current partial bars (matches backtest behavior)
                # The backtest uses sync_bar.htf_* which includes incomplete bars
                df_1h = None
                df_15m = None
                dxy_1h = None

                # Build GC 1H buffer INCLUDING current partial bar
                gc_1h_with_partial = list(self.df_1h_buffer)
                if self._gc_1h_start is not None:
                    gc_1h_with_partial.append(
                        {
                            "timestamp": self._gc_1h_start,
                            "open": self._gc_1h_open,
                            "high": self._gc_1h_high,
                            "low": self._gc_1h_low,
                            "close": self._gc_1h_close,
                            "volume": self._gc_1h_volume,
                        }
                    )
                if len(gc_1h_with_partial) > 0:
                    df_1h = pd.DataFrame(gc_1h_with_partial)

                # Build GC 15M buffer INCLUDING current partial bar
                gc_15m_with_partial = list(self.df_15m_buffer)
                if self._gc_15m_start is not None:
                    gc_15m_with_partial.append(
                        {
                            "timestamp": self._gc_15m_start,
                            "open": self._gc_15m_open,
                            "high": self._gc_15m_high,
                            "low": self._gc_15m_low,
                            "close": self._gc_15m_close,
                            "volume": self._gc_15m_volume,
                        }
                    )
                if len(gc_15m_with_partial) > 0:
                    df_15m = pd.DataFrame(gc_15m_with_partial)

                # DXY 1H buffer handling for chop detection
                # The backtest caches chop value and only recalculates at specific boundaries:
                # - At 1H close: include partial bar (nearly complete)
                # - At new hour (non-first session): include partial bar to check if chop clears
                # - At other times: use completed bars only (cache chop value)
                current_hour = gc_bar.timestamp.hour
                should_include_dxy_partial = is_1h_close or (
                    is_new_hour and current_hour != self._first_hour_of_session
                )

                if len(self.dxy_1h_buffer) > 0:
                    if should_include_dxy_partial:
                        # Include the current partial bar (last entry in buffer)
                        dxy_1h = pd.DataFrame(self.dxy_1h_buffer)
                    else:
                        # Use completed bars only - exclude the current partial bar
                        # (which is the last entry being updated in-place)
                        if (
                            self._current_dxy_1h_in_buffer
                            and len(self.dxy_1h_buffer) > 1
                        ):
                            # Exclude last entry (current partial bar)
                            dxy_1h = pd.DataFrame(self.dxy_1h_buffer[:-1])
                        else:
                            dxy_1h = pd.DataFrame(self.dxy_1h_buffer)

                # Update swept levels tracking before computing bias
                # This detects which swing highs/lows have been violated
                self._update_swept_levels(gc_bar)

                # Call existing HTF bias calculator
                # Combine swept levels into a single set for untouched liquidity computation
                combined_swept_levels = self.swept_levels_high | self.swept_levels_low

                self.current_htf_bias = compute_htf_bias(
                    features_1h=self.features_1h,
                    features_15m=self.features_15m,
                    features_1m=self.features_1m,  # Pass 1M features for DXY alignment
                    dxy_1h=dxy_1h,
                    df_15m=df_15m,
                    df_1h=df_1h,
                    sweep_events_15m=None,  # TODO: Add liquidity sweep detection
                    timestamp=pd.Timestamp(gc_bar.timestamp),
                    swept_levels=combined_swept_levels,
                )

                # Cache DXY chop value at boundaries, use cached value otherwise
                if should_include_dxy_partial:
                    # Update cache with newly calculated chop value
                    self._cached_dxy_chop = self.current_htf_bias.dxy_chop_detected
                else:
                    # Use cached chop value (override computed value)
                    # This is important because at mid-hour, the computed value
                    # might incorrectly clear chop due to using completed bars only
                    # We want to preserve the chop state from the last boundary
                    if self.current_htf_bias.dxy_chop_detected != self._cached_dxy_chop:
                        # Create updated HTFBias with cached chop value
                        self.current_htf_bias = HTFBias(
                            bias=self.current_htf_bias.bias,
                            direction=self.current_htf_bias.direction,
                            score=self.current_htf_bias.score,
                            confidence=self.current_htf_bias.confidence,
                            structure_15m=self.current_htf_bias.structure_15m,
                            structure_1h=self.current_htf_bias.structure_1h,
                            dxy_alignment=self.current_htf_bias.dxy_alignment,
                            chop_detected=self.current_htf_bias.chop_detected,
                            dxy_chop_detected=self._cached_dxy_chop,  # Use cached
                            vwap_trend_confirmed=self.current_htf_bias.vwap_trend_confirmed,
                            seasonality_adjustment=self.current_htf_bias.seasonality_adjustment,
                            seasonality_period=self.current_htf_bias.seasonality_period,
                            bos_detected=self.current_htf_bias.bos_detected,
                            bars_since_bos=self.current_htf_bias.bars_since_bos,
                            choch_detected=self.current_htf_bias.choch_detected,
                            fvg_alignment_score=self.current_htf_bias.fvg_alignment_score,
                            confirmation_candle=self.current_htf_bias.confirmation_candle,
                            bos_candle=self.current_htf_bias.bos_candle,
                            conflict_detected=self.current_htf_bias.conflict_detected,
                            conflict_reason=self.current_htf_bias.conflict_reason,
                            structure_clarity=self.current_htf_bias.structure_clarity,
                            liquidity_sweep_detected=self.current_htf_bias.liquidity_sweep_detected,
                            # TP Structural Target fields (SOP Section 4.3)
                            htf_range_high=self.current_htf_bias.htf_range_high,
                            htf_range_low=self.current_htf_bias.htf_range_low,
                            untouched_liquidity_high=self.current_htf_bias.untouched_liquidity_high,
                            untouched_liquidity_low=self.current_htf_bias.untouched_liquidity_low,
                            nearest_fvg_high=self.current_htf_bias.nearest_fvg_high,
                            nearest_fvg_low=self.current_htf_bias.nearest_fvg_low,
                            # Opposing FVG fields (critical for TP safety checks)
                            opposing_fvg_high=self.current_htf_bias.opposing_fvg_high,
                            opposing_fvg_low=self.current_htf_bias.opposing_fvg_low,
                            opposing_fvg_bullish_high=self.current_htf_bias.opposing_fvg_bullish_high,
                            opposing_fvg_bullish_low=self.current_htf_bias.opposing_fvg_bullish_low,
                        )

                logger.debug(
                    f"HTF bias updated: {self.current_htf_bias.bias} "
                    f"(score: {self.current_htf_bias.score:.1f}, "
                    f"confidence: {self.current_htf_bias.confidence}, "
                    f"dxy_chop={self.current_htf_bias.dxy_chop_detected})"
                )

                # Update current_1h_timestamp to track hour changes properly
                self.current_1h_timestamp = gc_bar.timestamp

                return self.current_htf_bias

            except Exception as e:
                logger.error(f"HTF bias calculation failed: {e}", exc_info=True)

        # Update current_1h_timestamp even when HTF bias isn't recalculated
        # This ensures is_new_hour is only True when the hour actually changes
        if (
            self.current_1h_timestamp is None
            or self.current_1h_timestamp.hour != current_hour
        ):
            self.current_1h_timestamp = gc_bar.timestamp

        return None

    def _is_15m_boundary(self, timestamp: datetime) -> bool:
        """Check if timestamp is at a 15M bar boundary.

        Args:
            timestamp: Current timestamp

        Returns:
            True if this is the last 1M bar of a 15M period
        """
        # 15M boundaries occur when minute is 14, 29, 44, or 59
        return timestamp.minute % 15 == 14

    def _is_1h_boundary(self, timestamp: datetime) -> bool:
        """Check if timestamp is at a 1H bar boundary.

        Args:
            timestamp: Current timestamp

        Returns:
            True if this is the last 1M bar of a 1H period
        """
        # 1H boundaries occur when minute is 59
        return timestamp.minute == 59

    def _update_15m_aggregation(self, gc_bar: Candle) -> None:
        """Update 15M GC candle aggregation with new 1M bar."""
        period_start = self._get_15m_start(gc_bar.timestamp)

        if self._gc_15m_start is None or self._gc_15m_start != period_start:
            # New period - reset aggregation
            self._gc_15m_start = period_start
            self._gc_15m_open = gc_bar.open
            self._gc_15m_high = gc_bar.high
            self._gc_15m_low = gc_bar.low
            self._gc_15m_close = gc_bar.close
            self._gc_15m_volume = gc_bar.volume
        else:
            # Same period - update aggregation
            if gc_bar.high > (self._gc_15m_high or 0):
                self._gc_15m_high = gc_bar.high
            if gc_bar.low < (self._gc_15m_low or float("inf")):
                self._gc_15m_low = gc_bar.low
            self._gc_15m_close = gc_bar.close
            self._gc_15m_volume += gc_bar.volume

    def _update_1h_aggregation(self, gc_bar: Candle, dxy_bar: Candle) -> None:
        """Update 1H GC and DXY candle aggregation with new 1M bars."""
        period_start = self._get_1h_start(gc_bar.timestamp)

        # GC aggregation
        if self._gc_1h_start is None or self._gc_1h_start != period_start:
            # New period - reset aggregation
            self._gc_1h_start = period_start
            self._gc_1h_open = gc_bar.open
            self._gc_1h_high = gc_bar.high
            self._gc_1h_low = gc_bar.low
            self._gc_1h_close = gc_bar.close
            self._gc_1h_volume = gc_bar.volume
        else:
            # Same period - update aggregation
            if gc_bar.high > (self._gc_1h_high or 0):
                self._gc_1h_high = gc_bar.high
            if gc_bar.low < (self._gc_1h_low or float("inf")):
                self._gc_1h_low = gc_bar.low
            self._gc_1h_close = gc_bar.close
            self._gc_1h_volume += gc_bar.volume

        # DXY aggregation - mimics backtest buffer behavior where the last entry
        # is updated in-place as the bar develops (shared object reference)
        if self._dxy_1h_start is None or self._dxy_1h_start != period_start:
            # New period - reset aggregation
            self._dxy_1h_start = period_start
            self._dxy_1h_open = dxy_bar.open
            self._dxy_1h_high = dxy_bar.high
            self._dxy_1h_low = dxy_bar.low
            self._dxy_1h_close = dxy_bar.close

            # Add new entry to DXY buffer (will be updated in-place)
            self.dxy_1h_buffer.append(
                {
                    "timestamp": period_start,
                    "open": dxy_bar.open,
                    "high": dxy_bar.high,
                    "low": dxy_bar.low,
                    "close": dxy_bar.close,
                }
            )
            self._current_dxy_1h_in_buffer = True

            # Limit buffer size
            max_buffer_size = 200
            if len(self.dxy_1h_buffer) > max_buffer_size:
                self.dxy_1h_buffer = self.dxy_1h_buffer[-max_buffer_size:]
        else:
            # Same period - update aggregation
            if dxy_bar.high > (self._dxy_1h_high or 0):
                self._dxy_1h_high = dxy_bar.high
            if dxy_bar.low < (self._dxy_1h_low or float("inf")):
                self._dxy_1h_low = dxy_bar.low
            self._dxy_1h_close = dxy_bar.close

            # Update the last buffer entry in-place (like backtest's shared reference)
            if self._current_dxy_1h_in_buffer and len(self.dxy_1h_buffer) > 0:
                self.dxy_1h_buffer[-1] = {
                    "timestamp": self._dxy_1h_start,
                    "open": self._dxy_1h_open,
                    "high": self._dxy_1h_high,
                    "low": self._dxy_1h_low,
                    "close": self._dxy_1h_close,
                }

    def _emit_15m_to_buffer(self) -> None:
        """Emit completed 15M aggregated candle to buffer and reset."""
        if self._gc_15m_start is None:
            return

        self.df_15m_buffer.append(
            {
                "timestamp": self._gc_15m_start,
                "open": self._gc_15m_open,
                "high": self._gc_15m_high,
                "low": self._gc_15m_low,
                "close": self._gc_15m_close,
                "volume": self._gc_15m_volume,
            }
        )

        # Limit buffer size (keep last 200 bars = ~2 days)
        max_buffer_size = 200
        if len(self.df_15m_buffer) > max_buffer_size:
            self.df_15m_buffer = self.df_15m_buffer[-max_buffer_size:]

        # Reset aggregation for next period
        self._gc_15m_start = None
        self._gc_15m_open = None
        self._gc_15m_high = None
        self._gc_15m_low = None
        self._gc_15m_close = None
        self._gc_15m_volume = 0.0

    def _add_to_15m_buffer(self, gc_bar: Candle) -> None:
        """Add a 15M GC bar directly to the buffer.

        Used for warmup and testing. For streaming, use update() instead.

        Args:
            gc_bar: 15M GC candle to add
        """
        self.df_15m_buffer.append(
            {
                "timestamp": gc_bar.timestamp,
                "open": gc_bar.open,
                "high": gc_bar.high,
                "low": gc_bar.low,
                "close": gc_bar.close,
                "volume": gc_bar.volume,
            }
        )

        # Limit buffer size (keep last 200 bars)
        max_buffer_size = 200
        if len(self.df_15m_buffer) > max_buffer_size:
            self.df_15m_buffer = self.df_15m_buffer[-max_buffer_size:]

    def _emit_1h_to_buffer(self) -> None:
        """Emit completed 1H aggregated candles to buffers and reset."""
        if self._gc_1h_start is None:
            return

        # Add GC bar
        self.df_1h_buffer.append(
            {
                "timestamp": self._gc_1h_start,
                "open": self._gc_1h_open,
                "high": self._gc_1h_high,
                "low": self._gc_1h_low,
                "close": self._gc_1h_close,
                "volume": self._gc_1h_volume,
            }
        )

        # DXY bar is already in buffer (updated in-place during aggregation)
        # Just do a final update to ensure it has the complete data
        if self._current_dxy_1h_in_buffer and len(self.dxy_1h_buffer) > 0:
            self.dxy_1h_buffer[-1] = {
                "timestamp": self._dxy_1h_start,
                "open": self._dxy_1h_open,
                "high": self._dxy_1h_high,
                "low": self._dxy_1h_low,
                "close": self._dxy_1h_close,
            }

        # Limit buffer size to prevent memory growth (keep last 200 bars = ~8 days)
        max_buffer_size = 200
        if len(self.df_1h_buffer) > max_buffer_size:
            self.df_1h_buffer = self.df_1h_buffer[-max_buffer_size:]
        if len(self.dxy_1h_buffer) > max_buffer_size:
            self.dxy_1h_buffer = self.dxy_1h_buffer[-max_buffer_size:]

        # Reset aggregation for next period
        self._gc_1h_start = None
        self._gc_1h_open = None
        self._gc_1h_high = None
        self._gc_1h_low = None
        self._gc_1h_close = None
        self._gc_1h_volume = 0.0
        self._dxy_1h_start = None
        self._dxy_1h_open = None
        self._dxy_1h_high = None
        self._dxy_1h_low = None
        self._dxy_1h_close = None
        self._current_dxy_1h_in_buffer = False

    def _add_to_1h_buffer(self, gc_bar: Candle, dxy_bar: Candle) -> None:
        """Add 1H GC and DXY bars directly to the buffers.

        Used for warmup and testing. For streaming, use update() instead.

        Args:
            gc_bar: 1H GC candle to add
            dxy_bar: 1H DXY candle to add
        """
        # Add GC bar
        self.df_1h_buffer.append(
            {
                "timestamp": gc_bar.timestamp,
                "open": gc_bar.open,
                "high": gc_bar.high,
                "low": gc_bar.low,
                "close": gc_bar.close,
                "volume": gc_bar.volume,
            }
        )

        # Add DXY bar
        self.dxy_1h_buffer.append(
            {
                "timestamp": dxy_bar.timestamp,
                "open": dxy_bar.open,
                "high": dxy_bar.high,
                "low": dxy_bar.low,
                "close": dxy_bar.close,
            }
        )

        # Limit buffer size (keep last 200 bars)
        max_buffer_size = 200
        if len(self.df_1h_buffer) > max_buffer_size:
            self.df_1h_buffer = self.df_1h_buffer[-max_buffer_size:]
        if len(self.dxy_1h_buffer) > max_buffer_size:
            self.dxy_1h_buffer = self.dxy_1h_buffer[-max_buffer_size:]

    def _get_15m_start(self, timestamp: datetime) -> datetime:
        """Get start timestamp of 15M period containing timestamp."""
        minute = timestamp.minute
        if minute < 15:
            start_minute = 0
        elif minute < 30:
            start_minute = 15
        elif minute < 45:
            start_minute = 30
        else:
            start_minute = 45
        return timestamp.replace(minute=start_minute, second=0, microsecond=0)

    def _get_1h_start(self, timestamp: datetime) -> datetime:
        """Get start timestamp of 1H period containing timestamp."""
        return timestamp.replace(minute=0, second=0, microsecond=0)

    def get_current_features_15m(self) -> pd.Series:
        """Get current 15M features.

        Returns:
            Series with current 15M features (empty if not yet available)
        """
        return self.features_15m

    def get_current_features_1h(self) -> pd.Series:
        """Get current 1H features.

        Returns:
            Series with current 1H features (empty if not yet available)
        """
        return self.features_1h

    def get_current_bias(self) -> HTFBias | None:
        """Get current HTF bias.

        Returns:
            Most recent HTFBias object, or None if not yet calculated
        """
        return self.current_htf_bias

    def _update_swept_levels(self, current_bar: Candle) -> None:
        """Update swept levels tracking based on current price action.

        A level is considered "swept" when price violates it (high exceeds swing high,
        or low breaks below swing low). This is used for untouched liquidity computation.

        Args:
            current_bar: Current 1M candle with high/low to check for sweeps

        Logic:
            - Check recent swing highs from df_1h_buffer
            - If current bar's high exceeds a swing high, mark it as swept
            - Similarly for swing lows
            - Reset swept levels at major structure breaks (BOS)
        """
        if len(self.df_1h_buffer) < 3:
            return  # Need at least 3 bars to identify swings

        # Get recent swing highs and lows from the 1H buffer
        # A simple swing high is a bar with high > neighbors
        # A simple swing low is a bar with low < neighbors
        for i in range(1, len(self.df_1h_buffer) - 1):
            prev_bar = self.df_1h_buffer[i - 1]
            curr_bar = self.df_1h_buffer[i]
            next_bar = self.df_1h_buffer[i + 1]

            # Check for swing high (local peak)
            if (
                curr_bar["high"] > prev_bar["high"]
                and curr_bar["high"] > next_bar["high"]
            ):
                swing_high = curr_bar["high"]
                # If current price exceeded this swing high, mark as swept
                if current_bar.high > swing_high:
                    self.swept_levels_high.add(swing_high)

            # Check for swing low (local trough)
            if curr_bar["low"] < prev_bar["low"] and curr_bar["low"] < next_bar["low"]:
                swing_low = curr_bar["low"]
                # If current price broke below this swing low, mark as swept
                if current_bar.low < swing_low:
                    self.swept_levels_low.add(swing_low)

        # Optional: Clear very old swept levels to prevent memory growth
        # Keep only levels from the recent buffer window
        if len(self.swept_levels_high) > 100:
            # Keep only recent levels (within reasonable price range)
            recent_highs = [bar["high"] for bar in self.df_1h_buffer[-20:]]
            if recent_highs:
                max_recent = max(recent_highs)
                min_recent = min(recent_highs)
                # Keep levels within 2x the recent range
                range_buffer = (max_recent - min_recent) * 2
                self.swept_levels_high = {
                    level
                    for level in self.swept_levels_high
                    if min_recent - range_buffer <= level <= max_recent + range_buffer
                }

        if len(self.swept_levels_low) > 100:
            recent_lows = [bar["low"] for bar in self.df_1h_buffer[-20:]]
            if recent_lows:
                max_recent = max(recent_lows)
                min_recent = min(recent_lows)
                range_buffer = (max_recent - min_recent) * 2
                self.swept_levels_low = {
                    level
                    for level in self.swept_levels_low
                    if min_recent - range_buffer <= level <= max_recent + range_buffer
                }

    def is_warmed_up(self) -> bool:
        """Check if calculator has enough data for reliable HTF bias.

        Returns:
            True if we have processed at least 1 complete 1H bar and 4 15M bars
        """
        # Need at least 1 complete 1H bar and 4 15M bars (1 hour) for meaningful context
        # The processor's is_warmed_up() check is too strict (requires 50 bars each)
        return len(self.df_1h_buffer) >= 1 and len(self.df_15m_buffer) >= 4

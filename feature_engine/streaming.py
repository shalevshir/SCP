"""Streaming Feature Processor for incremental indicator calculation.

This module provides StreamingFeatureProcessor that maintains state and calls
existing calculation functions to compute features incrementally as new bars arrive.

Architecture: Zero code duplication - reuses existing functions from feature_engine.
"""

from collections import deque
from datetime import datetime

import pandas as pd
from common.logger import get_logger
from common.types import Candle

from feature_engine.dxy_correlation import calculate_dxy_correlation
from feature_engine.rsi import calculate_rsi
from feature_engine.structure import calculate_structure_labels
from feature_engine.timezone_utils import get_vwap_session_id

logger = get_logger(__name__)


class StreamingFeatureProcessor:
    """Streaming processor that incrementally computes features.

    Maintains state buffers and calls existing calculation functions to ensure
    identical results between streaming and batch processing modes.

    Features calculated:
    - EMA (9, 20, 50): Incremental formula
    - VWAP: Cumulative, session-aware
    - RSI: Window-based, calls existing function
    - DXY Correlation: Window-based, calls existing function
    - Structure Labels: Lookback-based, calls existing function
    - VWAP Deviation: Calls existing function

    Attributes:
        timeframe: Target timeframe (e.g., "1m", "15m", "1h")
        ema_states: Dict of EMA state for each period (9, 20, 50)
        rsi_buffer: Deque of recent close prices for RSI calculation
        dxy_corr_gc_buffer: Deque of recent GC close prices for correlation
        dxy_corr_dxy_buffer: Deque of recent DXY close prices for correlation
        structure_buffer: Deque of recent OHLC data for structure detection
        vwap_pv_sum: Cumulative price*volume sum for VWAP
        vwap_v_sum: Cumulative volume sum for VWAP
        vwap_current_session: Current VWAP session ID
        rsi_avg_gain: Current average gain for RSI Wilder's smoothing
        rsi_avg_loss: Current average loss for RSI Wilder's smoothing
        prev_close: Previous close price for RSI delta calculation
    """

    @staticmethod
    def _get_buffer_size_for_timeframe(timeframe: str) -> int:
        """Determine appropriate buffer size based on timeframe.
        
        Higher timeframes need larger buffers to capture enough swing points.
        
        Args:
            timeframe: The timeframe string (e.g., "1m", "15m", "1h")
            
        Returns:
            Buffer size in bars
        """
        tf_lower = timeframe.lower()
        
        if "h" in tf_lower:  # 1h, 2h, 4h
            buffer_size = 100  # ~4 days for 1h
        elif "15m" in tf_lower:
            buffer_size = 50  # ~12.5 hours
        elif "5m" in tf_lower:
            buffer_size = 40  # ~3.3 hours
        else:  # 1m and others
            buffer_size = 30  # 30 minutes for 1m
        
        logger.debug(f"[StreamingProcessor] Buffer size for {timeframe}: {buffer_size} bars")
        return buffer_size

    def __init__(
        self,
        timeframe: str,
        rsi_period: int = 14,
        ema_periods: list[int] | None = None,
        dxy_window: int = 50,
        swing_window: int = 5,
        session_reset: bool = True,
    ):
        """Initialize streaming processor.

        Args:
            timeframe: Target timeframe (e.g., "1m", "15m", "1h")
            rsi_period: RSI calculation period (default: 14)
            ema_periods: List of EMA periods (default: [9, 20, 50])
            dxy_window: DXY correlation window (default: 50)
            swing_window: Structure label swing window (default: 5)
            session_reset: Whether to reset VWAP at session boundaries (default: True)
        """
        self.timeframe = timeframe
        self.rsi_period = rsi_period
        self.ema_periods = ema_periods if ema_periods is not None else [9, 20, 50]
        self.dxy_window = dxy_window
        self.swing_window = swing_window
        self.session_reset = session_reset

        # EMA state: {period: current_ema_value}
        self.ema_states: dict[int, float | None] = {
            period: None for period in self.ema_periods
        }
        self.ema_alphas: dict[int, float] = {
            period: 2.0 / (period + 1) for period in self.ema_periods
        }

        # RSI buffer and Wilder's smoothing state
        self.rsi_buffer: deque[float] = deque(maxlen=rsi_period + 1)
        self.rsi_avg_gain: float | None = None
        self.rsi_avg_loss: float | None = None
        self.prev_close: float | None = None

        # DXY correlation buffers (long window for HTF)
        self.dxy_corr_gc_buffer: deque[tuple[datetime, float]] = deque(
            maxlen=dxy_window
        )
        self.dxy_corr_dxy_buffer: deque[tuple[datetime, float]] = deque(
            maxlen=dxy_window
        )

        # Micro correlation buffers (5-bar window for short-term alignment)
        self.micro_corr_window = 5
        self.micro_corr_gc_buffer: deque[float] = deque(maxlen=self.micro_corr_window)
        self.micro_corr_dxy_buffer: deque[float] = deque(maxlen=self.micro_corr_window)

        # Structure detection buffer (needs enough bars to capture swing points)
        # Structure calculation requires 3*swing_window+1 bars minimum
        # Buffer size scales with timeframe to ensure adequate swing detection:
        # - 1m/5m: 30 bars (30-150 min of data)
        # - 15m: 50 bars (12.5 hours of data)  
        # - 1h: 100 bars (100 hours / ~4 days of data)
        buffer_size = self._get_buffer_size_for_timeframe(timeframe)
        self.structure_buffer: deque[dict] = deque(maxlen=buffer_size)
        self.dxy_structure_buffer: deque[dict] = deque(maxlen=buffer_size)
        
        logger.info(
            f"[StreamingFeatureProcessor] Initialized: timeframe={timeframe}, "
            f"swing_window={swing_window}, structure_buffer_size={buffer_size}"
        )

        # Track last detected structure label (persists between bars)
        self.last_structure_label: str | None = None
        self.last_dxy_structure_label: str | None = None

        # VWAP cumulative state
        self.vwap_pv_sum = 0.0
        self.vwap_v_sum = 0.0
        self.vwap_current_session: str | None = None

        # Warmup tracking
        self.bar_count = 0

    def update(self, gc_bar: Candle, dxy_bar: Candle) -> pd.Series:
        """Update state with new bar and return current features.

        Args:
            gc_bar: New Gold candle
            dxy_bar: New DXY candle (aligned timestamp)

        Returns:
            Series with current feature values
        """
        self.bar_count += 1
        features = {}

        # Store timestamp and basic OHLCV
        features["timestamp"] = gc_bar.timestamp
        features["open"] = gc_bar.open
        features["high"] = gc_bar.high
        features["low"] = gc_bar.low
        features["close"] = gc_bar.close
        features["volume"] = gc_bar.volume

        # === 1. EMA (incremental formula) ===
        for period in self.ema_periods:
            alpha = self.ema_alphas[period]
            if self.ema_states[period] is None:
                # Initialize with first close price
                self.ema_states[period] = gc_bar.close
            else:
                # EMA = price × α + EMA_prev × (1-α)
                self.ema_states[period] = gc_bar.close * alpha + self.ema_states[
                    period
                ] * (1 - alpha)
            features[f"ema_{period}"] = self.ema_states[period]

        # === 2. VWAP (cumulative, session-aware) ===
        # Check for session boundary
        session_id = get_vwap_session_id(gc_bar.timestamp)
        if self.session_reset and session_id != self.vwap_current_session:
            # Reset VWAP at session boundary
            self.vwap_pv_sum = 0.0
            self.vwap_v_sum = 0.0
            self.vwap_current_session = session_id
            logger.debug(
                f"VWAP session reset at {gc_bar.timestamp} (session: {session_id})"
            )

        # Calculate typical price and update cumulative sums
        typical_price = (gc_bar.high + gc_bar.low + gc_bar.close) / 3
        volume = max(gc_bar.volume, 1e-10)  # Prevent division by zero

        self.vwap_pv_sum += typical_price * volume
        self.vwap_v_sum += volume

        vwap = (
            self.vwap_pv_sum / self.vwap_v_sum if self.vwap_v_sum > 0 else gc_bar.close
        )
        features["vwap"] = vwap

        # === 3. VWAP Deviation ===
        if vwap > 0:
            features["vwap_deviation"] = abs((gc_bar.close - vwap) / vwap * 100)
        else:
            features["vwap_deviation"] = None

        # === 4. RSI (window-based, calls existing function) ===
        # Update RSI buffer
        self.rsi_buffer.append(gc_bar.close)

        if len(self.rsi_buffer) >= self.rsi_period + 1:
            # Convert buffer to DataFrame and call existing function
            df_rsi = pd.DataFrame({"close": list(self.rsi_buffer)})
            rsi_series = calculate_rsi(df_rsi, period=self.rsi_period)
            # Extract last value (most recent RSI)
            features["rsi"] = rsi_series.iloc[-1] if not rsi_series.empty else None
        else:
            features["rsi"] = None

        # === 5. DXY Correlation (window-based, calls existing function) ===
        # Update DXY correlation buffers
        self.dxy_corr_gc_buffer.append((gc_bar.timestamp, gc_bar.close))
        self.dxy_corr_dxy_buffer.append((dxy_bar.timestamp, dxy_bar.close))

        if len(self.dxy_corr_gc_buffer) >= self.dxy_window:
            # Convert buffers to DataFrames
            gc_data = list(self.dxy_corr_gc_buffer)
            dxy_data = list(self.dxy_corr_dxy_buffer)

            df_gc = pd.DataFrame(
                {
                    "ts_event": [item[0] for item in gc_data],
                    "close": [item[1] for item in gc_data],
                }
            )
            df_dxy = pd.DataFrame(
                {
                    "ts_event": [item[0] for item in dxy_data],
                    "close": [item[1] for item in dxy_data],
                }
            )

            # Call existing function
            try:
                corr_series = calculate_dxy_correlation(
                    df_gc, df_dxy, window=self.dxy_window
                )
                # Extract last value
                features["dxy_corr"] = (
                    corr_series.iloc[-1] if not corr_series.empty else None
                )
            except Exception as e:
                logger.warning(f"DXY correlation calculation failed: {e}")
                features["dxy_corr"] = None
        else:
            features["dxy_corr"] = None

        # === 5b. Micro Correlation (5-bar window for short-term alignment) ===
        # Update micro correlation buffers
        self.micro_corr_gc_buffer.append(gc_bar.close)
        self.micro_corr_dxy_buffer.append(dxy_bar.close)

        if len(self.micro_corr_gc_buffer) >= self.micro_corr_window:
            # Calculate Pearson correlation manually for 5-bar window
            gc_array = list(self.micro_corr_gc_buffer)
            dxy_array = list(self.micro_corr_dxy_buffer)

            gc_mean = sum(gc_array) / len(gc_array)
            dxy_mean = sum(dxy_array) / len(dxy_array)

            numerator = sum((gc - gc_mean) * (dxy - dxy_mean) for gc, dxy in zip(gc_array, dxy_array, strict=False))
            gc_std = (sum((gc - gc_mean) ** 2 for gc in gc_array)) ** 0.5
            dxy_std = (sum((dxy - dxy_mean) ** 2 for dxy in dxy_array)) ** 0.5

            if gc_std > 0 and dxy_std > 0:
                features["dxy_corr_micro"] = numerator / (gc_std * dxy_std)
            else:
                features["dxy_corr_micro"] = None
        else:
            features["dxy_corr_micro"] = None

        # === 6. Structure Labels (lookback-based, calls existing function) ===
        # Update structure buffer
        self.structure_buffer.append(
            {
                "timestamp": gc_bar.timestamp,
                "high": gc_bar.high,
                "low": gc_bar.low,
                "close": gc_bar.close,
            }
        )

        # Need enough bars for structure detection
        # The structure calculation loop requires: len(df) > 3 * swing_window
        # So we need at least 3 * swing_window + 1 bars for the loop to execute
        required_bars = 3 * self.swing_window + 1
        
        # Initialize with persisted value - will be updated if we detect a new swing
        current_label = self.last_structure_label
        
        if len(self.structure_buffer) >= required_bars:
            # Convert buffer to DataFrame
            df_structure = pd.DataFrame(list(self.structure_buffer))

            # Call existing function
            try:
                labels_series = calculate_structure_labels(
                    df_structure,
                    swing_window=self.swing_window,
                    high_column="high",
                    low_column="low",
                )
                # Get the latest confirmed structure label (non-NA swing point)
                # Structure labels are sparse - only exist at actual swing highs/lows
                # We need the most recent confirmed swing, not a fixed position
                valid_labels = labels_series.dropna()

                if len(valid_labels) > 0:
                    # Latest real swing point (HH/HL/LH/LL)
                    current_label = valid_labels.iloc[-1]
                    self.last_structure_label = current_label
                    logger.debug(
                        f"[{self.timeframe}] Structure updated -> {current_label}"
                    )
                else:
                    # No swings detected in buffer
                    if self.last_structure_label is None:
                        logger.debug(
                            f"[{self.timeframe}] No swings detected in {len(self.structure_buffer)}-bar buffer "
                            f"(swing_window={self.swing_window}). Consider increasing buffer size or swing_window."
                        )
            except Exception as e:
                logger.warning(f"Structure label calculation failed: {e}")
                # Keep current_label as self.last_structure_label

        # Return the current structure label (latest confirmed swing or persisted value)
        features["structure_label"] = current_label
        features["structure_type"] = current_label  # Alias for compatibility

        # === 7. DXY Structure Labels ===
        # Update DXY structure buffer
        self.dxy_structure_buffer.append(
            {
                "timestamp": dxy_bar.timestamp,
                "high": dxy_bar.high,
                "low": dxy_bar.low,
                "close": dxy_bar.close,
            }
        )

        # Initialize with persisted value
        current_dxy_label = self.last_dxy_structure_label

        if len(self.dxy_structure_buffer) >= required_bars:
            # Convert buffer to DataFrame
            df_dxy_structure = pd.DataFrame(list(self.dxy_structure_buffer))

            # Call existing function for DXY
            try:
                dxy_labels_series = calculate_structure_labels(
                    df_dxy_structure,
                    swing_window=self.swing_window,
                    high_column="high",
                    low_column="low",
                )
                # Get the latest confirmed DXY structure label
                valid_dxy_labels = dxy_labels_series.dropna()

                if len(valid_dxy_labels) > 0:
                    # Latest real swing point for DXY
                    current_dxy_label = valid_dxy_labels.iloc[-1]
                    self.last_dxy_structure_label = current_dxy_label
                    logger.debug(
                        f"[{self.timeframe}] DXY Structure updated -> {current_dxy_label}"
                    )
            except Exception as e:
                logger.warning(f"DXY structure label calculation failed: {e}")

        # Add DXY structure label to features
        features["dxy_structure_label"] = current_dxy_label

        return pd.Series(features)

    def is_warmed_up(self) -> bool:
        """Check if processor has enough data to produce reliable features.

        Returns:
            True if warmup period complete
        """
        min_warmup = max(
            max(self.ema_periods),
            self.rsi_period + 1,
            self.dxy_window,
            3 * self.swing_window + 1,  # Structure calculation needs 3*swing_window+1 bars
        )
        return self.bar_count >= min_warmup

    def reset(self) -> None:
        """Reset all state to initial conditions."""
        self.ema_states = {period: None for period in self.ema_periods}
        self.rsi_buffer.clear()
        self.rsi_avg_gain = None
        self.rsi_avg_loss = None
        self.prev_close = None
        self.dxy_corr_gc_buffer.clear()
        self.dxy_corr_dxy_buffer.clear()
        self.micro_corr_gc_buffer.clear()
        self.micro_corr_dxy_buffer.clear()
        self.structure_buffer.clear()
        self.dxy_structure_buffer.clear()
        self.last_structure_label = None
        self.last_dxy_structure_label = None
        self.vwap_pv_sum = 0.0
        self.vwap_v_sum = 0.0
        self.vwap_current_session = None
        self.bar_count = 0
        logger.info("Streaming feature processor reset")

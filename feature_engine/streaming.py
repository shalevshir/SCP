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
from feature_engine.structure import (
    StructureContextTracker,
    get_swing_window_for_timeframe,
)
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

        logger.debug(
            f"[StreamingProcessor] Buffer size for {timeframe}: " f"{buffer_size} bars"
        )
        return buffer_size

    def __init__(
        self,
        timeframe: str,
        rsi_period: int = 14,
        ema_periods: list[int] | None = None,
        dxy_window: int = 50,
        swing_window: int | None = None,
        session_reset: bool = True,
    ):
        """Initialize streaming processor.

        Args:
            timeframe: Target timeframe (e.g., "1m", "15m", "1h")
            rsi_period: RSI calculation period (default: 14)
            ema_periods: List of EMA periods (default: [9, 20, 50])
            dxy_window: DXY correlation window (default: 50)
            swing_window: Structure label swing window. If None, automatically
                         determined based on timeframe (1m=2, 15m=3, 1h=5).
                         Can be explicitly set to override default.
            session_reset: Whether to reset VWAP at session boundaries (default: True)
        """
        self.timeframe = timeframe
        self.rsi_period = rsi_period
        self.ema_periods = ema_periods if ema_periods is not None else [9, 20, 50]
        self.dxy_window = dxy_window

        # Automatically determine swing_window based on timeframe if not provided
        if swing_window is None:
            self.swing_window = get_swing_window_for_timeframe(timeframe)
        else:
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

        # Volume SMA buffer (20-period for volume spike detection)
        self.volume_sma_period = 20
        self.volume_buffer: deque[float] = deque(maxlen=self.volume_sma_period)

        # Structure context trackers (replaces old buffer-based approach)
        # Provides continuous structure state with derived fields on every bar
        clarity_window = 10  # Window for clarity/chop detection
        self.structure_tracker = StructureContextTracker(
            swing_window=self.swing_window,
            clarity_window=clarity_window,
            timeframe=self.timeframe,  # Pass timeframe for asset-adjusted ATR thresholds
        )
        self.dxy_structure_tracker = StructureContextTracker(
            swing_window=self.swing_window,
            clarity_window=clarity_window,
            timeframe=self.timeframe,  # DXY uses same timeframe
        )

        logger.info(
            f"[StreamingFeatureProcessor] Initialized: timeframe={timeframe}, "
            f"swing_window={self.swing_window}, clarity_window={clarity_window}"
        )

        # VWAP cumulative state
        self.vwap_pv_sum = 0.0
        self.vwap_v_sum = 0.0
        self.vwap_current_session: str | None = None
        self.prev_vwap: float | None = None  # For vwap_slope calculation

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

        # === 0. Volume SMA (20-period for volume spike detection) ===
        self.volume_buffer.append(gc_bar.volume)
        if len(self.volume_buffer) >= self.volume_sma_period:
            features["volume_sma_20"] = sum(self.volume_buffer) / len(
                self.volume_buffer
            )
        else:
            features["volume_sma_20"] = None

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

        # Calculate VWAP slope (rate of change for trend direction)
        if self.prev_vwap is not None:
            features["vwap_slope"] = vwap - self.prev_vwap
        else:
            features["vwap_slope"] = None
        self.prev_vwap = vwap

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

            numerator = sum(
                (gc - gc_mean) * (dxy - dxy_mean)
                for gc, dxy in zip(gc_array, dxy_array, strict=False)
            )
            gc_std = (sum((gc - gc_mean) ** 2 for gc in gc_array)) ** 0.5
            dxy_std = (sum((dxy - dxy_mean) ** 2 for dxy in dxy_array)) ** 0.5

            if gc_std > 0 and dxy_std > 0:
                features["dxy_corr_micro"] = numerator / (gc_std * dxy_std)
            else:
                features["dxy_corr_micro"] = None
        else:
            features["dxy_corr_micro"] = None

        # === 6. Structure Context (continuous state with derived fields) ===
        # Update GC structure tracker
        gc_structure_ctx = self.structure_tracker.update(
            high=gc_bar.high,
            low=gc_bar.low,
            close=gc_bar.close,
        )
        
        # Update VWAP tracking for second confirmation
        self.structure_tracker.update_vwap_state(
            vwap=vwap,
            close=gc_bar.close,
        )
        
        # Update volume tracking for expansion confirmation
        self.structure_tracker.update_volume_state(volume=gc_bar.volume)
        
        # Compute second confirmation for both directions
        long_conf = self.structure_tracker.compute_second_confirmation("long")
        short_conf = self.structure_tracker.compute_second_confirmation("short")

        # Add GC structure fields to features
        features["structure_label"] = gc_structure_ctx.last_structure_label
        # Alias for compatibility
        features["structure_type"] = gc_structure_ctx.last_structure_label
        features["last_structure_label"] = gc_structure_ctx.last_structure_label
        features["trend_direction"] = gc_structure_ctx.trend_direction
        features["trend_confidence"] = gc_structure_ctx.trend_confidence
        features["structure_clarity"] = gc_structure_ctx.structure_clarity
        features["is_chop"] = gc_structure_ctx.is_chop
        features["is_structural_chop"] = gc_structure_ctx.is_structural_chop
        features["atr_compression_ratio"] = gc_structure_ctx.atr_compression_ratio
        features["structure_conflict_flag"] = gc_structure_ctx.structure_conflict_flag
        features["last_swing_high"] = gc_structure_ctx.last_swing_high
        features["last_swing_low"] = gc_structure_ctx.last_swing_low
        features["last_swing_high_idx"] = gc_structure_ctx.last_swing_high_idx
        features["last_swing_low_idx"] = gc_structure_ctx.last_swing_low_idx
        features["bos_direction"] = gc_structure_ctx.bos_direction
        features["bos_recent"] = gc_structure_ctx.bos_recent
        features["bos_age"] = gc_structure_ctx.bos_age
        features["choch_detected"] = gc_structure_ctx.choch_detected
        features["choch_direction"] = gc_structure_ctx.choch_direction
        features["choch_age"] = gc_structure_ctx.choch_age
        features["liquidity_sweep"] = gc_structure_ctx.liquidity_sweep
        features["sweep_direction"] = gc_structure_ctx.sweep_direction
        features["sweep_price"] = gc_structure_ctx.sweep_price
        features["sweep_age"] = gc_structure_ctx.sweep_age

        # === 6b. Expansion Detection (for VWAP_RECLAIM entry timing) ===
        # Detect expansion signals to determine if market is resolving from compression
        expansion_detected, expansion_reasons = self.structure_tracker.detect_expansion()
        features["expansion_detected"] = expansion_detected
        features["expansion_reasons"] = expansion_reasons

        # === 7. DXY Structure Context ===
        # Update DXY structure tracker
        dxy_structure_ctx = self.dxy_structure_tracker.update(
            high=dxy_bar.high,
            low=dxy_bar.low,
            close=dxy_bar.close,
        )

        # Add DXY structure fields to features
        features["dxy_structure_label"] = dxy_structure_ctx.last_structure_label
        features["dxy_trend_direction"] = dxy_structure_ctx.trend_direction
        features["dxy_structure_clarity"] = dxy_structure_ctx.structure_clarity
        features["dxy_is_chop"] = dxy_structure_ctx.is_chop
        
        # === 8. Second Confirmation for VWAP_RECLAIM ===
        features["second_confirmation_long"] = long_conf["confirmed"]
        features["second_confirmation_short"] = short_conf["confirmed"]
        features["second_confirmation_long_type"] = long_conf["confirmation_type"]
        features["second_confirmation_short_type"] = short_conf["confirmation_type"]
        features["second_confirmation_long_reasons"] = long_conf["reasons"]
        features["second_confirmation_short_reasons"] = short_conf["reasons"]
        features["bars_since_vwap_reclaim"] = long_conf["bars_since_reclaim"]

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
            # Structure calculation needs 3*swing_window+1 bars
            3 * self.swing_window + 1,
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
        self.volume_buffer.clear()

        # Reset structure trackers
        clarity_window = 10
        self.structure_tracker = StructureContextTracker(
            swing_window=self.swing_window,
            clarity_window=clarity_window,
            timeframe=self.timeframe,  # Pass timeframe for asset-adjusted ATR thresholds
        )
        self.dxy_structure_tracker = StructureContextTracker(
            swing_window=self.swing_window,
            clarity_window=clarity_window,
            timeframe=self.timeframe,  # DXY uses same timeframe
        )

        self.vwap_pv_sum = 0.0
        self.vwap_v_sum = 0.0
        self.vwap_current_session = None
        self.prev_vwap = None
        self.bar_count = 0
        logger.info("Streaming feature processor reset")

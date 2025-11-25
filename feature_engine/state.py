"""Incremental FeatureState Engine for real-time feature calculation.

This module provides stateful feature calculators that process candles one at a time,
maintaining all indicator state (VWAP, RSI, EMA, DXY correlation, structure labels)
without look-ahead bias. Designed for realistic backtesting and live trading.
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING

from common.logger import get_logger
from feature_engine.timezone_utils import get_vwap_session_id

if TYPE_CHECKING:
    from common.types import Candle

logger = get_logger(__name__)


@dataclass
class VWAPState:
    """State tracker for VWAP calculation with session resets."""

    cum_pv: float = 0.0  # Cumulative price × volume
    cum_volume: float = 0.0
    current_session_date: date | None = None
    session_reset: bool = True

    def update(self, candle: Candle) -> float:
        """Update VWAP state with new candle and return current VWAP.

        VWAP resets at 08:20 AM Eastern Time (RTH open for Gold futures).
        Sessions run from 08:20 ET to 08:19:59 ET next day.

        Args:
            candle: New candle to process

        Returns:
            Current VWAP value
        """
        # Compute session ID based on 08:20 ET reset time
        session_id = get_vwap_session_id(candle.timestamp)

        # Check for session boundary (session ID change)
        if self.session_reset and self.current_session_date is not None:
            if session_id != self.current_session_date:
                # New session - reset cumulative values
                logger.debug(
                    f"VWAP session reset: {self.current_session_date} -> {session_id}"
                )
                self.cum_pv = 0.0
                self.cum_volume = 0.0

        # Update current session ID
        self.current_session_date = session_id

        # Calculate typical price
        typical_price = (candle.high + candle.low + candle.close) / 3

        # Handle zero volume by using epsilon
        volume = candle.volume if candle.volume > 0 else np.finfo(float).eps

        # Update cumulative sums
        self.cum_pv += typical_price * volume
        self.cum_volume += volume

        # Calculate and return VWAP
        vwap = self.cum_pv / self.cum_volume
        return vwap


@dataclass
class RSIState:
    """State tracker for RSI calculation using Wilder's smoothing."""

    period: int = 14
    avg_gain: float | None = None
    avg_loss: float | None = None
    prev_price: float | None = None
    gain_buffer: list[float] = field(default_factory=list)
    loss_buffer: list[float] = field(default_factory=list)
    period_count: int = 0

    def update(self, price: float) -> float | None:
        """Update RSI state with new price and return current RSI.

        Args:
            price: Current close price

        Returns:
            Current RSI value (0-100), or None if not enough data
        """
        # First price - just store it
        if self.prev_price is None:
            self.prev_price = price
            return None

        # Calculate price change (delta)
        delta = price - self.prev_price
        self.prev_price = price

        # Separate into gain and loss
        gain = delta if delta > 0 else 0.0
        loss = -delta if delta < 0 else 0.0

        self.period_count += 1

        # Initial period: accumulate in buffers
        if self.period_count <= self.period:
            self.gain_buffer.append(gain)
            self.loss_buffer.append(loss)

            # Calculate first RSI after period candles
            if self.period_count == self.period:
                self.avg_gain = sum(self.gain_buffer) / self.period
                self.avg_loss = sum(self.loss_buffer) / self.period

                # Calculate first RSI
                if self.avg_loss == 0:
                    return 100.0 if self.avg_gain > 0 else 50.0
                else:
                    rs = self.avg_gain / self.avg_loss
                    return 100.0 - (100.0 / (1.0 + rs))
            else:
                return None

        # Subsequent periods: Wilder's smoothing
        else:
            # Wilder's formula: new_avg = (prev_avg * (period-1) + current_value) / period
            self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
            self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period

            # Calculate RSI
            if self.avg_loss == 0:
                return 100.0 if self.avg_gain > 0 else 50.0
            else:
                rs = self.avg_gain / self.avg_loss
                return 100.0 - (100.0 / (1.0 + rs))


@dataclass
class EMAState:
    """State tracker for multiple EMA calculations."""

    periods: list[int] = field(default_factory=lambda: [9, 20, 50])
    ema_values: dict[int, float] = field(default_factory=dict)
    first_price: float | None = None

    def update(self, price: float) -> dict[str, float]:
        """Update EMA state with new price and return current EMAs.

        Args:
            price: Current close price

        Returns:
            Dict mapping "ema_{period}" to current EMA value
        """
        # Initialize with first price if needed
        if self.first_price is None:
            self.first_price = price
            for period in self.periods:
                self.ema_values[period] = price
            return {f"ema_{period}": price for period in self.periods}

        # Update each EMA using formula: price × α + ema_prev × (1 - α)
        # where α = 2 / (period + 1)
        result = {}
        for period in self.periods:
            alpha = 2.0 / (period + 1)
            prev_ema = self.ema_values[period]
            new_ema = price * alpha + prev_ema * (1 - alpha)
            self.ema_values[period] = new_ema
            result[f"ema_{period}"] = new_ema

        return result


@dataclass
class DXYCorrelationState:
    """State tracker for rolling GC-DXY correlation."""

    window: int = 50
    gc_prices: deque[float] = field(default_factory=lambda: deque(maxlen=50))
    dxy_prices: deque[float] = field(default_factory=lambda: deque(maxlen=50))
    timestamps: deque[datetime] = field(default_factory=lambda: deque(maxlen=50))

    def __post_init__(self):
        """Initialize deques with correct maxlen."""
        if not isinstance(self.gc_prices, deque):
            self.gc_prices = deque(self.gc_prices, maxlen=self.window)
        if not isinstance(self.dxy_prices, deque):
            self.dxy_prices = deque(self.dxy_prices, maxlen=self.window)
        if not isinstance(self.timestamps, deque):
            self.timestamps = deque(self.timestamps, maxlen=self.window)

    def update(
        self, gc_price: float | None, dxy_price: float | None, timestamp: datetime
    ) -> float | None:
        """Update correlation state and return current correlation.

        Args:
            gc_price: GC close price (can be None if no GC update)
            dxy_price: DXY close price (can be None if no DXY update)
            timestamp: Timestamp for this update

        Returns:
            Current correlation value (-1 to 1), or None if not enough data
        """
        # Only add to buffers if both prices are provided
        if gc_price is not None and dxy_price is not None:
            self.gc_prices.append(gc_price)
            self.dxy_prices.append(dxy_price)
            self.timestamps.append(timestamp)

        # Need full window to calculate correlation
        if len(self.gc_prices) < self.window:
            return None

        # Calculate Pearson correlation
        gc_array = np.array(self.gc_prices)
        dxy_array = np.array(self.dxy_prices)

        # Calculate means
        gc_mean = gc_array.mean()
        dxy_mean = dxy_array.mean()

        # Calculate correlation
        numerator = ((gc_array - gc_mean) * (dxy_array - dxy_mean)).sum()
        gc_std = np.sqrt(((gc_array - gc_mean) ** 2).sum())
        dxy_std = np.sqrt(((dxy_array - dxy_mean) ** 2).sum())

        if gc_std == 0 or dxy_std == 0:
            return 0.0

        correlation = numerator / (gc_std * dxy_std)
        return float(correlation)


@dataclass
class StructureState:
    """State tracker for structure label calculation (HH/HL/LH/LL).
    
    CRITICAL: This implementation avoids look-ahead bias by only using
    past data from the buffer. Swing points are identified when we have
    enough historical context to confirm them.
    """

    swing_window: int = 5
    high_buffer: deque[float] = field(default_factory=lambda: deque(maxlen=11))
    low_buffer: deque[float] = field(default_factory=lambda: deque(maxlen=11))
    prev_swing_high: float | None = None
    prev_swing_low: float | None = None

    def __post_init__(self):
        """Initialize deques with correct maxlen."""
        maxlen = self.swing_window * 2 + 1
        if not isinstance(self.high_buffer, deque):
            self.high_buffer = deque(self.high_buffer, maxlen=maxlen)
        if not isinstance(self.low_buffer, deque):
            self.low_buffer = deque(self.low_buffer, maxlen=maxlen)

    def update(self, high: float, low: float) -> str | None:
        """Update structure state and return structure label if swing point detected.

        Args:
            high: Current candle high
            low: Current candle low

        Returns:
            Structure label ("HH", "HL", "LH", "LL"), or None if not a swing point
            or not enough data yet.
        """
        # Add to buffers
        self.high_buffer.append(high)
        self.low_buffer.append(low)

        # Need full buffer to identify swing points
        if len(self.high_buffer) < self.swing_window * 2 + 1:
            return None

        # Check if the CENTER point of the buffer is a swing point
        # This ensures we only use past data (no look-ahead)
        center_idx = self.swing_window
        center_high = self.high_buffer[center_idx]
        center_low = self.low_buffer[center_idx]

        # Check if center is a swing high (local maximum)
        is_swing_high = all(
            center_high >= self.high_buffer[i]
            for i in range(len(self.high_buffer))
            if i != center_idx
        )

        # Check if center is a swing low (local minimum)
        is_swing_low = all(
            center_low <= self.low_buffer[i]
            for i in range(len(self.low_buffer))
            if i != center_idx
        )

        label = None

        # Process swing high
        if is_swing_high:
            if self.prev_swing_high is not None:
                if center_high > self.prev_swing_high:
                    label = "HH"
                elif center_high < self.prev_swing_high:
                    label = "LH"
                else:
                    label = "HH"  # Equal - default to HH
            else:
                # First swing high
                label = "HH"
            self.prev_swing_high = center_high

        # Process swing low (only if not already labeled as swing high)
        elif is_swing_low:
            if self.prev_swing_low is not None:
                if center_low > self.prev_swing_low:
                    label = "HL"
                elif center_low < self.prev_swing_low:
                    label = "LL"
                else:
                    label = "HL"  # Equal - default to HL
            else:
                # First swing low
                label = "HL"
            self.prev_swing_low = center_low

        return label


class FeatureState:
    """Incremental feature calculator with full trading environment state.
    
    Processes GC and DXY candles one at a time, maintaining all indicator state
    without look-ahead bias. Supports asynchronous instrument updates.
    """

    def __init__(
        self,
        timeframe: str,
        session_reset: bool = True,
        rsi_period: int = 14,
        ema_periods: list[int] | None = None,
        dxy_window: int = 50,
        swing_window: int = 5,
    ):
        """Initialize FeatureState with configuration.

        Args:
            timeframe: Timeframe string (e.g., "1m", "15m", "1h")
            session_reset: Whether to reset VWAP at session boundaries
            rsi_period: Period for RSI calculation (default 14)
            ema_periods: List of EMA periods (default [9, 20, 50])
            dxy_window: Window for DXY correlation (default 50)
            swing_window: Window for structure label detection (default 5)
        """
        # Initialize all state objects
        self._vwap_state = VWAPState(session_reset=session_reset)
        self._rsi_state = RSIState(period=rsi_period)
        self._ema_state = EMAState(periods=ema_periods or [9, 20, 50])
        self._dxy_corr_state = DXYCorrelationState(window=dxy_window)
        self._structure_state = StructureState(swing_window=swing_window)

        # Synchronization tracking
        self._last_gc_candle: Candle | None = None
        self._last_dxy_candle: Candle | None = None
        self._last_gc_ts: datetime | None = None
        self._last_dxy_ts: datetime | None = None
        self._candle_count: int = 0

        # Configuration
        self.timeframe = timeframe
        self.rsi_period = rsi_period
        self.dxy_window = dxy_window
        self.swing_window = swing_window
        self.max_warmup = max(dxy_window, swing_window * 2 + 1)

    def update(
        self,
        gc_candle: Candle | None = None,
        dxy_candle: Candle | None = None,
    ) -> pd.Series | None:
        """Update state with new candle(s) and return features.

        Args:
            gc_candle: GC candle (can be None if only DXY update)
            dxy_candle: DXY candle (can be None if only GC update)

        Returns:
            pd.Series with feature values, or None if not ready (warmup incomplete).
            Series contains: timestamp, symbol, timeframe, open, high, low, close, volume,
            vwap, rsi, ema_9, ema_20, ema_50, dxy_corr, structure_label, vwap_deviation.

        Raises:
            ValueError: If neither candle is provided
        """
        # Validate at least one candle provided
        if gc_candle is None and dxy_candle is None:
            raise ValueError("At least one of gc_candle or dxy_candle must be provided")

        # Update GC state if provided
        if gc_candle is not None:
            # Check for out-of-order updates
            if self._last_gc_ts is not None and gc_candle.timestamp < self._last_gc_ts:
                logger.warning(
                    f"Out-of-order GC candle: {gc_candle.timestamp} < {self._last_gc_ts}"
                )

            self._last_gc_candle = gc_candle
            self._last_gc_ts = gc_candle.timestamp
            self._candle_count += 1

        # Update DXY state if provided
        if dxy_candle is not None:
            # Check for out-of-order updates
            if self._last_dxy_ts is not None and dxy_candle.timestamp < self._last_dxy_ts:
                logger.warning(
                    f"Out-of-order DXY candle: {dxy_candle.timestamp} < {self._last_dxy_ts}"
                )

            self._last_dxy_candle = dxy_candle
            self._last_dxy_ts = dxy_candle.timestamp

        # If no GC candle yet, can't compute features
        if self._last_gc_candle is None:
            return None

        # Update all indicators with current GC candle
        gc = self._last_gc_candle

        # VWAP
        vwap = self._vwap_state.update(gc)

        # RSI
        rsi = self._rsi_state.update(gc.close)

        # EMA
        ema_dict = self._ema_state.update(gc.close)

        # DXY Correlation (requires both GC and DXY)
        gc_price = gc.close if gc_candle is not None else None
        dxy_price = self._last_dxy_candle.close if self._last_dxy_candle is not None else None
        timestamp = gc.timestamp
        dxy_corr = self._dxy_corr_state.update(gc_price, dxy_price, timestamp)

        # Structure labels
        structure_label = self._structure_state.update(gc.high, gc.low)

        # VWAP deviation
        if vwap > 0:
            vwap_deviation = abs((gc.close - vwap) / vwap * 100)
        else:
            vwap_deviation = None

        # Build features Series
        features = pd.Series(
            {
                "timestamp": gc.timestamp,
                "symbol": gc.symbol,
                "timeframe": gc.timeframe,
                "open": gc.open,
                "high": gc.high,
                "low": gc.low,
                "close": gc.close,
                "volume": gc.volume,
                "vwap": vwap,
                "rsi": rsi,
                **ema_dict,
                "dxy_corr": dxy_corr,
                "structure_label": structure_label,
                "vwap_deviation": vwap_deviation,
            }
        )

        return features

    def is_ready(self) -> bool:
        """Check if past warmup period.

        Returns:
            True if enough candles processed for all indicators to be valid
        """
        return self._candle_count >= self.max_warmup

    def warmup_remaining(self) -> int:
        """Return number of candles needed to complete warmup.

        Returns:
            Number of candles until all indicators are ready (0 if ready)
        """
        return max(0, self.max_warmup - self._candle_count)

    def get_features(self) -> pd.Series:
        """Get current feature values (may contain NaN if not ready).

        Returns:
            pd.Series with current feature values. May contain NaN for
            indicators that haven't completed warmup yet.
        """
        if self._last_gc_candle is None:
            # Return empty Series with expected columns
            return pd.Series(
                {
                    "timestamp": None,
                    "symbol": None,
                    "timeframe": self.timeframe,
                    "open": None,
                    "high": None,
                    "low": None,
                    "close": None,
                    "volume": None,
                    "vwap": None,
                    "rsi": None,
                    "ema_9": None,
                    "ema_20": None,
                    "ema_50": None,
                    "dxy_corr": None,
                    "structure_label": None,
                    "vwap_deviation": None,
                }
            )

        gc = self._last_gc_candle

        # Get current values (may be None/NaN if not ready)
        vwap = self._vwap_state.cum_pv / self._vwap_state.cum_volume if self._vwap_state.cum_volume > 0 else None
        
        # RSI - calculate current value if ready
        rsi = None
        if self._rsi_state.avg_gain is not None and self._rsi_state.avg_loss is not None:
            if self._rsi_state.avg_loss == 0:
                rsi = 100.0 if self._rsi_state.avg_gain > 0 else 50.0
            else:
                rs = self._rsi_state.avg_gain / self._rsi_state.avg_loss
                rsi = 100.0 - (100.0 / (1.0 + rs))

        # EMA - get current values
        ema_9 = self._ema_state.ema_values.get(9)
        ema_20 = self._ema_state.ema_values.get(20)
        ema_50 = self._ema_state.ema_values.get(50)

        # DXY correlation - get current value if ready
        dxy_corr = None
        if len(self._dxy_corr_state.gc_prices) >= self.dxy_window:
            gc_array = np.array(self._dxy_corr_state.gc_prices)
            dxy_array = np.array(self._dxy_corr_state.dxy_prices)
            gc_mean = gc_array.mean()
            dxy_mean = dxy_array.mean()
            numerator = ((gc_array - gc_mean) * (dxy_array - dxy_mean)).sum()
            gc_std = np.sqrt(((gc_array - gc_mean) ** 2).sum())
            dxy_std = np.sqrt(((dxy_array - dxy_mean) ** 2).sum())
            if gc_std > 0 and dxy_std > 0:
                dxy_corr = numerator / (gc_std * dxy_std)

        # Structure label - None if not at a swing point
        structure_label = None

        # VWAP deviation
        vwap_deviation = None
        if vwap is not None and vwap > 0:
            vwap_deviation = abs((gc.close - vwap) / vwap * 100)

        return pd.Series(
            {
                "timestamp": gc.timestamp,
                "symbol": gc.symbol,
                "timeframe": gc.timeframe,
                "open": gc.open,
                "high": gc.high,
                "low": gc.low,
                "close": gc.close,
                "volume": gc.volume,
                "vwap": vwap,
                "rsi": rsi,
                "ema_9": ema_9,
                "ema_20": ema_20,
                "ema_50": ema_50,
                "dxy_corr": dxy_corr,
                "structure_label": structure_label,
                "vwap_deviation": vwap_deviation,
            }
        )


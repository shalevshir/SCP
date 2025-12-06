"""Dashboard State - Immutable dataclass for dashboard state.

This module provides a strictly typed, immutable DashboardState that holds
all current dashboard information including features, HTF bias, signals,
and price history.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal, Optional

import pandas as pd

from rule_engine.htf.types import HTFBias
from rule_engine.signal import Signal


@dataclass(frozen=True)
class PriceBar:
    """Immutable price bar for chart history.

    Attributes:
        timestamp: Bar timestamp
        open: Opening price
        high: High price
        low: Low price
        close: Closing price
        volume: Trading volume (optional, default 0)
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class DashboardState:
    """Immutable dashboard state container.

    Holds all information needed to render dashboard panels including
    current features, HTF bias, signals, session constraints, and
    historical data for charting.

    Use `update()` to create new state with modified fields.

    Attributes:
        timestamp: Current simulation timestamp
        features: Current 15M features (VWAP, RSI, EMAs, etc.)
        htf_bias: Current HTF bias object
        current_signal: Current trade signal (if any)
        session_constraints: Current session constraints (name, min_score)
        is_session_active: Whether trading session is active
        is_simulation_running: Whether simulation is actively running
        is_paused: Whether simulation is paused (manually or auto)
        pause_reason: Reason for pause (if paused)
        paused_at_signal: Signal that triggered auto-pause (if any)
        simulation_speed: Speed multiplier for simulation
        simulation_progress: Progress through simulation (0.0 to 1.0)
        price_history_gc: Tuple of recent GC price bars for charting
        price_history_dxy: Tuple of recent DXY price bars for charting
        max_history_size: Maximum bars to keep in history buffers
    """

    # Core state
    timestamp: Optional[datetime] = None
    features: pd.Series = field(default_factory=lambda: pd.Series(dtype=object))
    htf_bias: Optional[HTFBias] = None
    current_signal: Optional[Signal] = None

    # Session
    session_constraints: Optional[dict[str, object]] = None
    is_session_active: bool = False

    # Simulation control
    is_simulation_running: bool = False
    is_paused: bool = False
    pause_reason: Optional[str] = None
    paused_at_signal: Optional[Signal] = None
    simulation_speed: float = 1.0
    simulation_progress: float = 0.0

    # Price history (immutable tuples)
    price_history_gc: tuple[PriceBar, ...] = ()
    price_history_dxy: tuple[PriceBar, ...] = ()
    max_history_size: int = 100

    def __hash__(self) -> int:
        """Hash based on timestamp for basic identity."""
        return hash(self.timestamp)

    def __eq__(self, other: object) -> bool:
        """Equality based on timestamp."""
        if not isinstance(other, DashboardState):
            return False
        return self.timestamp == other.timestamp

    @classmethod
    def create_empty(cls) -> DashboardState:
        """Create an empty dashboard state.

        Returns:
            DashboardState with all fields initialized to defaults.
        """
        return cls()

    def update(self, **kwargs: object) -> DashboardState:
        """Create new state with updated fields.

        Args:
            **kwargs: Fields to update

        Returns:
            New DashboardState with updated values
        """
        return replace(self, **kwargs)

    def with_price_bars(
        self, gc_bar: PriceBar, dxy_bar: PriceBar
    ) -> DashboardState:
        """Create new state with appended price bars.

        Maintains max_history_size limit by dropping oldest bars.

        Args:
            gc_bar: New GC price bar
            dxy_bar: New DXY price bar

        Returns:
            New DashboardState with updated price history
        """
        # Append and trim GC history
        new_gc = self.price_history_gc + (gc_bar,)
        if len(new_gc) > self.max_history_size:
            new_gc = new_gc[-self.max_history_size :]

        # Append and trim DXY history
        new_dxy = self.price_history_dxy + (dxy_bar,)
        if len(new_dxy) > self.max_history_size:
            new_dxy = new_dxy[-self.max_history_size :]

        return self.update(price_history_gc=new_gc, price_history_dxy=new_dxy)

    def get_price_history_gc_df(self) -> pd.DataFrame:
        """Get GC price history as DataFrame.

        Returns:
            DataFrame with GC OHLCV data
        """
        if not self.price_history_gc:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "timestamp": bar.timestamp,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in self.price_history_gc
            ]
        )

    def get_price_history_dxy_df(self) -> pd.DataFrame:
        """Get DXY price history as DataFrame.

        Returns:
            DataFrame with DXY OHLC data
        """
        if not self.price_history_dxy:
            return pd.DataFrame()

        return pd.DataFrame(
            [
                {
                    "timestamp": bar.timestamp,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                }
                for bar in self.price_history_dxy
            ]
        )

    def to_dict(self) -> dict[str, object]:
        """Convert state to dictionary for JSON serialization.

        Returns:
            Dictionary representation of state
        """
        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "is_session_active": self.is_session_active,
            "is_simulation_running": self.is_simulation_running,
            "is_paused": self.is_paused,
            "pause_reason": self.pause_reason,
            "simulation_speed": self.simulation_speed,
            "simulation_progress": self.simulation_progress,
            "features": self.features.to_dict() if not self.features.empty else {},
            "htf_bias": self._serialize_htf_bias(),
            "current_signal": self._serialize_signal(),
            "session_constraints": self.session_constraints,
        }

    def _serialize_htf_bias(self) -> Optional[dict[str, object]]:
        """Serialize HTF bias to dict."""
        if not self.htf_bias:
            return None
        return {
            "bias": self.htf_bias.bias,
            "direction": self.htf_bias.direction,
            "score": self.htf_bias.score,
            "confidence": self.htf_bias.confidence,
            "structure_1h": self.htf_bias.structure_1h,
            "structure_15m": self.htf_bias.structure_15m,
            "dxy_alignment": self.htf_bias.dxy_alignment,
            "vwap_trend_confirmed": self.htf_bias.vwap_trend_confirmed,
        }

    def _serialize_signal(self) -> Optional[dict[str, object]]:
        """Serialize signal to dict."""
        if not self.current_signal:
            return None
        return {
            "direction": self.current_signal.direction,
            "score": self.current_signal.score,
            "confidence": self.current_signal.confidence,
            "setup_type": self.current_signal.setup_type,
            "htf_bias": self.current_signal.htf_bias,
            "rationale": self.current_signal.rationale,
        }


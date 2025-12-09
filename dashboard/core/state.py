"""Dashboard State - Immutable dataclass for dashboard state.

This module provides a strictly typed, immutable DashboardState that holds
all current dashboard information including features, HTF bias, signals,
and price history.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

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
    timestamp: datetime | None = None
    features: pd.Series = field(default_factory=lambda: pd.Series(dtype=object))
    htf_bias: HTFBias | None = None
    current_signal: Signal | None = None

    # Session
    session_constraints: dict[str, object] | None = None
    is_session_active: bool = False

    # Simulation control
    is_simulation_running: bool = False
    is_paused: bool = False
    pause_reason: str | None = None
    paused_at_signal: Signal | None = None
    simulation_speed: float = 1.0
    simulation_progress: float = 0.0

    # Price history (immutable tuples)
    price_history_gc: tuple[PriceBar, ...] = ()
    price_history_dxy: tuple[PriceBar, ...] = ()
    max_history_size: int = 100

    def __hash__(self) -> int:
        """Hash based on all fields for proper identity.

        Converts non-hashable fields (pd.Series, dict) to hashable
        representations to ensure correct equality semantics.
        """
        return hash(
            (
                self.timestamp,
                self._hash_series(self.features),
                self._hash_htf_bias(self.htf_bias),
                self.current_signal,  # Signal is frozen, so hashable
                self._hash_dict(self.session_constraints),
                self.is_session_active,
                self.is_simulation_running,
                self.is_paused,
                self.pause_reason,
                self.paused_at_signal,  # Signal is frozen, so hashable
                self.simulation_speed,
                self.simulation_progress,
                self.price_history_gc,
                self.price_history_dxy,
                self.max_history_size,
            )
        )

    def __eq__(self, other: object) -> bool:
        """Equality based on all fields.

        Two states are equal only if all their fields are equal,
        ensuring proper dataclass semantics.
        """
        if not isinstance(other, DashboardState):
            return False
        return (
            self.timestamp == other.timestamp
            and self._eq_series(self.features, other.features)
            and self._eq_htf_bias(self.htf_bias, other.htf_bias)
            and self.current_signal == other.current_signal
            and self._eq_dict(self.session_constraints, other.session_constraints)
            and self.is_session_active == other.is_session_active
            and self.is_simulation_running == other.is_simulation_running
            and self.is_paused == other.is_paused
            and self.pause_reason == other.pause_reason
            and self.paused_at_signal == other.paused_at_signal
            and self.simulation_speed == other.simulation_speed
            and self.simulation_progress == other.simulation_progress
            and self.price_history_gc == other.price_history_gc
            and self.price_history_dxy == other.price_history_dxy
            and self.max_history_size == other.max_history_size
        )

    @staticmethod
    def _hash_series(series: pd.Series) -> int:
        """Convert pd.Series to hashable representation.

        Args:
            series: Pandas Series to hash

        Returns:
            Hash value of the series. Empty series hash to hash(()).
            Non-empty series are converted to sorted tuple of (index, value) pairs.
        """
        if series.empty:
            return hash(())
        # Convert to tuple of (index, value) pairs, sorted by index for consistency
        items = tuple(sorted((idx, val) for idx, val in series.items()))
        return hash(items)

    @staticmethod
    def _eq_series(s1: pd.Series, s2: pd.Series) -> bool:
        """Compare two pd.Series for equality.

        Args:
            s1: First pandas Series
            s2: Second pandas Series

        Returns:
            True if series are equal (same index and values), False otherwise.
            Uses pandas' equals() method with fallback to manual comparison.
        """
        if s1.empty and s2.empty:
            return True
        if s1.empty or s2.empty:
            return False
        # Use pandas' built-in equality check
        try:
            return s1.equals(s2)
        except Exception:
            # Fallback to manual comparison if equals() fails
            return len(s1) == len(s2) and all(
                s1.index[i] == s2.index[i] and s1.iloc[i] == s2.iloc[i]
                for i in range(len(s1))
            )

    @staticmethod
    def _hash_htf_bias(bias: HTFBias | None) -> int:
        """Convert HTFBias to hashable representation.

        Args:
            bias: HTFBias object or None

        Returns:
            Hash value of the bias. None hashes to hash(None).
            Non-None bias objects are converted to tuple of all field values.
        """
        if bias is None:
            return hash(None)
        # HTFBias is a dataclass, convert to tuple of field values
        return hash(
            (
                bias.bias,
                bias.direction,
                bias.score,
                bias.confidence,
                bias.structure_1h,
                bias.structure_15m,
                bias.bos_detected,
                bias.choch_detected,
                bias.liquidity_sweep_detected,
                bias.liquidity_sweep_type,
                bias.vwap_1h,
                bias.vwap_distance_1h,
                bias.vwap_slope_1h,
                bias.vwap_trend_confirmed,
                bias.fvg_alignment_score,
                bias.seasonality_period,
                bias.seasonality_adjustment,
                bias.dxy_corr_1h,
                bias.dxy_corr_15m,
                bias.dxy_chop_detected,
                bias.dxy_alignment,
                bias.conflict_detected,
                bias.conflict_reason,
            )
        )

    @staticmethod
    def _eq_htf_bias(b1: HTFBias | None, b2: HTFBias | None) -> bool:
        """Compare two HTFBias objects for equality.

        Args:
            b1: First HTFBias object or None
            b2: Second HTFBias object or None

        Returns:
            True if both are None or all fields are equal, False otherwise.
        """
        if b1 is None and b2 is None:
            return True
        if b1 is None or b2 is None:
            return False
        # Compare all fields
        return (
            b1.bias == b2.bias
            and b1.direction == b2.direction
            and b1.score == b2.score
            and b1.confidence == b2.confidence
            and b1.structure_1h == b2.structure_1h
            and b1.structure_15m == b2.structure_15m
            and b1.bos_detected == b2.bos_detected
            and b1.choch_detected == b2.choch_detected
            and b1.liquidity_sweep_detected == b2.liquidity_sweep_detected
            and b1.liquidity_sweep_type == b2.liquidity_sweep_type
            and b1.vwap_1h == b2.vwap_1h
            and b1.vwap_distance_1h == b2.vwap_distance_1h
            and b1.vwap_slope_1h == b2.vwap_slope_1h
            and b1.vwap_trend_confirmed == b2.vwap_trend_confirmed
            and b1.fvg_alignment_score == b2.fvg_alignment_score
            and b1.seasonality_period == b2.seasonality_period
            and b1.seasonality_adjustment == b2.seasonality_adjustment
            and b1.dxy_corr_1h == b2.dxy_corr_1h
            and b1.dxy_corr_15m == b2.dxy_corr_15m
            and b1.dxy_chop_detected == b2.dxy_chop_detected
            and b1.dxy_alignment == b2.dxy_alignment
            and b1.conflict_detected == b2.conflict_detected
            and b1.conflict_reason == b2.conflict_reason
        )

    @staticmethod
    def _hash_dict(d: dict[str, object] | None) -> int:
        """Convert dict to hashable representation.

        Args:
            d: Dictionary to hash or None

        Returns:
            Hash value of the dict. None hashes to hash(None).
            Attempts to use frozenset of items; falls back to string
            representation if dict contains unhashable values.
        """
        if d is None:
            return hash(None)
        # Convert to frozenset of items for hashing
        try:
            return hash(frozenset(d.items()))
        except TypeError:
            # If dict contains unhashable values, fall back to string representation
            return hash(str(sorted(d.items())))

    @staticmethod
    def _eq_dict(
        d1: dict[str, object] | None, d2: dict[str, object] | None
    ) -> bool:
        """Compare two dicts for equality.

        Args:
            d1: First dictionary or None
            d2: Second dictionary or None

        Returns:
            True if both are None or dicts are equal, False otherwise.
        """
        if d1 is None and d2 is None:
            return True
        if d1 is None or d2 is None:
            return False
        return d1 == d2

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

    def with_price_bars(self, gc_bar: PriceBar, dxy_bar: PriceBar) -> DashboardState:
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

    def _serialize_htf_bias(self) -> dict[str, object] | None:
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

    def _serialize_signal(self) -> dict[str, object] | None:
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
